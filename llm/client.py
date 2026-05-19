"""LLM 客户端：OpenAI SDK 封装 + Token 计数"""

import logging
from typing import Any

from openai import OpenAI

from config.settings import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """基于 OpenAI SDK 的 LLM 客户端，支持 base_url 切换模型"""

    def __init__(self, config: LLMConfig):
        self.config = config
        kwargs: dict[str, Any] = {
            "api_key": config.api_key or "sk-placeholder",
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = OpenAI(**kwargs)
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """非流式调用 LLM，返回完整响应"""
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = self.client.chat.completions.create(**kwargs)

        # 统计 Token 用量
        if response.usage:
            self._total_input_tokens += response.usage.prompt_tokens
            self._total_output_tokens += response.usage.completion_tokens

        return self._parse_response(response)

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ):
        """流式调用 LLM，yield 增量内容"""
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools

        stream = self.client.chat.completions.create(**kwargs)

        tool_calls_accum: dict[int, dict[str, Any]] = {}
        current_content = ""
        current_reasoning = ""
        usage = None

        for chunk in stream:
            # 捕获 usage（DeepSeek 流式最后一个 chunk 在顶层带 usage）
            if hasattr(chunk, 'usage') and chunk.usage:
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                }
                self._total_input_tokens += chunk.usage.prompt_tokens
                self._total_output_tokens += chunk.usage.completion_tokens

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # 文本内容增量
            if delta.content:
                current_content += delta.content
                yield {"type": "content_delta", "content": delta.content}

            # reasoning_content 增量拼接
            if getattr(delta, 'reasoning_content', None):
                current_reasoning += delta.reasoning_content

            # tool_calls 增量拼接
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_accum:
                        tool_calls_accum[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    acc = tool_calls_accum[idx]
                    if tc_delta.id:
                        acc["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            acc["function"]["arguments"] += tc_delta.function.arguments

            # 流结束
            if chunk.choices[0].finish_reason:
                result: dict[str, Any] = {
                    "type": "done",
                    "finish_reason": chunk.choices[0].finish_reason,
                    "content": current_content,
                }
                if tool_calls_accum:
                    result["tool_calls"] = [
                        tool_calls_accum[i]
                        for i in sorted(tool_calls_accum.keys())
                    ]
                if current_reasoning:
                    result["reasoning_content"] = current_reasoning
                if usage:
                    result["usage"] = usage
                yield result
                return

        # 兜底：流异常结束
        result_fallback: dict[str, Any] = {
            "type": "done",
            "finish_reason": "stop",
            "content": current_content,
        }
        if tool_calls_accum:
            result_fallback["tool_calls"] = [
                tool_calls_accum[i]
                for i in sorted(tool_calls_accum.keys())
            ]
        if current_reasoning:
            result_fallback["reasoning_content"] = current_reasoning
        if usage:
            result_fallback["usage"] = usage
        yield result_fallback

    def _parse_response(self, response) -> dict[str, Any]:
        """解析非流式响应为统一格式"""
        choice = response.choices[0]
        message = choice.message

        result: dict[str, Any] = {
            "finish_reason": choice.finish_reason,
            "content": message.content or "",
        }

        if getattr(message, 'reasoning_content', None):
            result["reasoning_content"] = message.reasoning_content

        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        return result

    def count_tokens(self, text: str) -> int:
        """简单估算 Token 数（中文约 1.5 字/token，英文约 4 字符/token）"""
        chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)
