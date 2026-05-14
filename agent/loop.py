"""Agent 主循环：迭代 LLM 调用 + 工具执行"""

import logging
from typing import Any

from llm.client import LLMClient

logger = logging.getLogger(__name__)


class AgentLoop:
    """Agent 主循环，驱动 LLM 与工具的交互"""

    def __init__(self, llm: LLMClient, max_iterations: int = 50):
        self.llm = llm
        self.max_iterations = max_iterations
        self.messages: list[dict[str, Any]] = []

    def run(self, user_message: str, system_prompt: str) -> str:
        """运行一轮对话，返回最终回复文本

        Args:
            user_message: 用户输入
            system_prompt: 系统提示词

        Returns:
            Agent 的最终文本回复
        """
        # 初始化消息列表
        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            logger.debug("Agent loop iteration %d/%d", iteration, self.max_iterations)

            # 调用 LLM（流式）
            response = self._call_llm_stream()

            # 无工具调用 → 返回最终回复
            if not response.get("tool_calls"):
                return response.get("content", "")

            # 有工具调用 → 当前 Checkpoint 不支持，直接返回
            logger.warning("Tool calls received but not supported in minimal loop")
            return response.get("content") or "（收到工具调用请求，但当前版本暂不支持工具执行）"

        # 预算耗尽
        logger.warning("Agent loop reached max iterations: %d", self.max_iterations)
        return self._grace_call()

    def _call_llm_stream(self) -> dict[str, Any]:
        """流式调用 LLM，实时输出内容，返回完整响应"""
        content_parts: list[str] = []
        tool_calls = None
        finish_reason = None

        for event in self.llm.chat_stream(self.messages):
            if event["type"] == "content_delta":
                content_parts.append(event["content"])
                # 实时输出到终端（简单 print，后续由 CLI 层接管）
                print(event["content"], end="", flush=True)
            elif event["type"] == "done":
                content_parts.append("")  # 确保内容完整
                tool_calls = event.get("tool_calls")
                finish_reason = event.get("finish_reason", "stop")

        full_content = "".join(content_parts)
        print()  # 换行

        # 构造助手消息并追加
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": full_content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        self.messages.append(assistant_msg)

        return {
            "content": full_content,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
        }

    def _grace_call(self) -> str:
        """预算耗尽后的最后一次调用，让 LLM 产出最终回复"""
        logger.info("Performing grace call")
        self.messages.append({
            "role": "user",
            "content": "请总结当前进展并给出最终回复。",
        })

        response = self._call_llm_stream()
        return response.get("content", "")
