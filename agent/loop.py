"""Agent 主循环：迭代 LLM 调用 + 工具执行 + 会话持久化"""

import logging
import uuid
from typing import Any, Callable

from agent.budget import IterationBudget
from db.session import SessionDB
from llm.client import LLMClient
from tools.registry import registry

logger = logging.getLogger(__name__)


class AgentLoop:
    """Agent 主循环，驱动 LLM 与工具的交互"""

    def __init__(
        self,
        llm: LLMClient,
        max_iterations: int = 50,
        session_db: SessionDB | None = None,
        output_callback: Callable[[str], None] | None = None,
    ):
        self.llm = llm
        self.max_iterations = max_iterations
        self.session_db = session_db
        self.output_callback = output_callback or self._default_output
        self.messages: list[dict[str, Any]] = []
        self.session_id: str | None = None
        self.budget = IterationBudget(max_iterations)

    def _default_output(self, text: str) -> None:
        """默认输出方法（简单 print）"""
        print(text, end="", flush=True)

    def _ensure_conversation_started(self, system_prompt: str, first_user_message: str) -> None:
        """初始化当前 AgentLoop 生命周期内的连续对话"""
        if not self.messages:
            self.messages.append({"role": "system", "content": system_prompt})

        if self.session_db and not self.session_id:
            self.session_id = str(uuid.uuid4())
            self.session_db.create_session(
                self.session_id,
                self.llm.model,
                system_prompt,
                title=first_user_message[:50],
            )

    def run(self, user_message: str, system_prompt: str) -> str:
        """运行一轮对话，返回最终回复文本

        Args:
            user_message: 用户输入
            system_prompt: 系统提示词

        Returns:
            Agent 的最终文本回复
        """
        # 初始化预算
        self.budget.reset()

        self._ensure_conversation_started(system_prompt, user_message)

        user_msg = {"role": "user", "content": user_message}
        self.messages.append(user_msg)

        if self.session_db and self.session_id:
            self.session_db.append_message(self.session_id, "user", content=user_message)
            self.session_db.update_session_stats(self.session_id, message_count=1)

        # 获取工具定义
        tools = registry.get_definitions()

        # 主循环
        while self.budget.can_continue():
            self.budget.consume()
            logger.debug("Agent loop iteration, budget remaining: %d", self.budget.remaining)

            # 调用 LLM（流式）
            response = self._call_llm_stream(tools=tools if tools else None)

            # 更新 token 统计
            if self.session_db and self.session_id:
                usage = response.get("usage")
                if usage:
                    self.session_db.update_session_stats(
                        self.session_id,
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                    )

            # 无工具调用 → 返回最终回复
            if not response.get("tool_calls"):
                result = response.get("content", "")
                self._persist_assistant_message(response)
                return result

            # 有工具调用 → 执行工具
            self._persist_assistant_message(response)
            tool_results = self._execute_tool_calls(response["tool_calls"])
            self.messages.extend(tool_results)

            # 持久化工具结果
            if self.session_db and self.session_id:
                for tr in tool_results:
                    self.session_db.append_message(
                        self.session_id,
                        "tool",
                        content=tr.get("content", ""),
                        tool_call_id=tr.get("tool_call_id"),
                    )
                    self.session_db.update_session_stats(self.session_id, message_count=1)
                self.session_db.update_session_stats(
                    self.session_id,
                    tool_call_count=len(response["tool_calls"]),
                )

        # 预算耗尽
        logger.warning("Agent loop reached max iterations: %d", self.max_iterations)
        return self._grace_call()

    def _call_llm_stream(self, tools: list[dict] | None = None) -> dict[str, Any]:
        """流式调用 LLM，实时输出内容，返回完整响应"""
        content_parts: list[str] = []
        tool_calls = None
        finish_reason = None
        reasoning_content = None
        usage = None

        for event in self.llm.chat_stream(self.messages, tools=tools):
            if event["type"] == "content_delta":
                content_parts.append(event["content"])
                self.output_callback(event["content"])
            elif event["type"] == "done":
                tool_calls = event.get("tool_calls")
                finish_reason = event.get("finish_reason", "stop")
                reasoning_content = event.get("reasoning_content")
                usage = event.get("usage")

        full_content = "".join(content_parts)
        self.output_callback("\n")

        # 构造助手消息并追加
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": full_content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        if reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        self.messages.append(assistant_msg)

        result: dict[str, Any] = {
            "content": full_content,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
        }
        if reasoning_content:
            result["reasoning_content"] = reasoning_content
        if usage:
            result["usage"] = usage

        return result

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """执行工具调用列表

        Args:
            tool_calls: LLM 返回的 tool_calls

        Returns:
            工具结果消息列表
        """
        logger.info("Executing %d tool calls", len(tool_calls))
        results = registry.dispatch_parallel(tool_calls)
        for i, result in enumerate(results):
            tool_name = tool_calls[i]["function"]["name"] if i < len(tool_calls) else "unknown"
            logger.info("Tool %s result: %s", tool_name, result.get("content", "")[:100])
        return results

    def _persist_assistant_message(self, response: dict[str, Any]) -> None:
        """持久化助手消息"""
        if not self.session_db or not self.session_id:
            return

        self.session_db.append_message(
            self.session_id,
            "assistant",
            content=response.get("content"),
            reasoning_content=response.get("reasoning_content"),
            tool_calls=response.get("tool_calls"),
            finish_reason=response.get("finish_reason"),
        )
        self.session_db.update_session_stats(self.session_id, message_count=1)

    def _grace_call(self) -> str:
        """预算耗尽后的最后一次调用，让 LLM 产出最终回复"""
        logger.info("Performing grace call")
        self.messages.append({
            "role": "user",
            "content": "请总结当前进展并给出最终回复。",
        })

        if self.session_db and self.session_id:
            self.session_db.append_message(
                self.session_id, "user", content="请总结当前进展并给出最终回复。"
            )
            self.session_db.update_session_stats(self.session_id, message_count=1)

        tools = registry.get_definitions()
        response = self._call_llm_stream(tools=tools if tools else None)

        if self.session_db and self.session_id:
            usage = response.get("usage")
            if usage:
                self.session_db.update_session_stats(
                    self.session_id,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                )

        self._persist_assistant_message(response)
        return response.get("content", "")
