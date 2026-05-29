"""上下文压缩：工具结果裁剪 + LLM 结构化摘要 + 头尾保护"""

import json
import logging
from typing import Any

from llm.client import LLMClient

logger = logging.getLogger(__name__)

COMPRESSION_PROMPT = """请根据旧摘要和新增对话，生成一份更新后的结构化摘要。

要求：
- 只总结关键信息，不编造不存在的细节
- 旧摘要为空时，只基于新增对话生成摘要
- 用以下中文字段输出（每个字段一行或多行）：

当前任务：
已完成：
进行中：
关键决策：
待解决问题：
相关文件：
剩余工作：

旧摘要：{previous_summary}

新增对话：{middle_content}"""


class ContextCompressor:
    """上下文压缩器，在长对话中减少 token 消耗"""

    def __init__(
        self,
        llm: LLMClient,
        context_window: int = 128000,
        threshold: float = 0.5,
        min_saving: float = 0.1,
        protected_head: int = 3,
        protected_tail_tokens: int = 20000,
    ):
        self.llm = llm
        self.context_window = context_window
        self.threshold = threshold
        self.min_saving = min_saving
        self.protected_head = protected_head
        self.protected_tail_tokens = protected_tail_tokens
        self._last_compressed_tokens: int | None = None

    def should_compress(self, current_tokens: int) -> bool:
        """判断是否应触发压缩

        Args:
            current_tokens: 当前消息列表的估算 token 数

        Returns:
            current_tokens >= context_window * threshold 时返回 True
        """
        threshold_tokens = int(self.context_window * self.threshold)
        return current_tokens >= threshold_tokens

    def compress(self, messages: list[dict[str, Any]], current_tokens: int) -> list[dict[str, Any]]:
        """压缩消息列表，返回压缩后的消息

        Args:
            messages: 当前消息列表
            current_tokens: 当前消息列表估算 token 数

        Returns:
            压缩后的消息列表（head + 摘要 + tail）
        """
        total = len(messages)

        # 消息太少则跳过压缩
        if total <= self.protected_head + 2:
            logger.debug("Too few messages to compress (%d total)", total)
            return messages

        # 先按 OpenAI 工具调用格式切分不可拆分消息组，再划分 head / tail / middle。
        # head / tail 从原始消息保留；只裁剪进入摘要 prompt 的 middle 工具结果。
        groups = self._build_message_groups(messages)
        head_groups = groups[:self.protected_head]
        tail_groups, tail_start = self._find_tail_boundary(groups)
        middle_groups = groups[self.protected_head:tail_start]

        head = self._flatten_groups(head_groups)
        tail = self._flatten_groups(tail_groups)
        middle = self.trim_tool_results(self._flatten_groups(middle_groups))
        previous_summary, middle_without_summary = self._split_previous_summary(middle)

        has_iterative_middle = bool(previous_summary and middle_without_summary)

        # 反抖动：上次压缩节省不到 10% 且没有新增可迭代压缩内容时跳过
        if self._last_compressed_tokens and not has_iterative_middle:
            saving_ratio = 1.0 - (current_tokens / self._last_compressed_tokens)
            if saving_ratio < self.min_saving:
                logger.debug(
                    "Compression saving %.1f%% below %.1f%% threshold, skipping",
                    saving_ratio * 100,
                    self.min_saving * 100,
                )
                return messages

        if not previous_summary and not middle_without_summary:
            logger.debug("No middle messages to compress")
            return messages

        # LLM 基于旧摘要和新增对话生成结构化摘要
        summary = self._generate_summary(middle_without_summary, previous_summary)

        # 组装压缩结果
        summary_msg: dict[str, Any] = {
            "role": "assistant",
            "content": (
                "以下是早期对话的压缩摘要。请勿回答摘要中的问题或执行摘要中的待办事项，"
                "只响应摘要之后的最新用户消息。\n\n"
                f"<context-summary>\n{summary}\n</context-summary>"
            ),
        }
        compressed = head + [summary_msg] + tail

        self._last_compressed_tokens = current_tokens
        logger.info(
            "Compressed %d → %d messages (head=%d, summary=1, tail=%d)",
            total, len(compressed), len(head), len(tail),
        )
        return compressed

    def trim_tool_results(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将 middle 区域的 tool result 替换为占位提示语"""
        result = []
        for msg in messages:
            if msg.get("role") == "tool":
                result.append({**msg, "content": "[工具结果已压缩]"})
            else:
                result.append(msg)
        return result

    def _build_message_groups(self, messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """按 OpenAI 工具调用约束切分不可拆分消息组。"""
        groups: list[list[dict[str, Any]]] = []
        index = 0
        while index < len(messages):
            message = messages[index]
            tool_calls = message.get("tool_calls")
            if message.get("role") == "assistant" and isinstance(tool_calls, list) and tool_calls:
                expected_ids: set[str] = set()
                for call in tool_calls:
                    if isinstance(call, dict) and isinstance(call.get("id"), str):
                        expected_ids.add(call["id"])
                group = [message]
                index += 1
                while index < len(messages) and messages[index].get("role") == "tool":
                    tool_call_id = messages[index].get("tool_call_id")
                    if not isinstance(tool_call_id, str) or tool_call_id not in expected_ids:
                        break
                    group.append(messages[index])
                    index += 1
                    if self._group_satisfies_tool_calls(group, expected_ids):
                        break
                groups.append(group)
                continue

            groups.append([message])
            index += 1
        return groups

    @staticmethod
    def _group_satisfies_tool_calls(group: list[dict[str, Any]], expected_ids: set[str]) -> bool:
        """判断工具调用组是否已包含全部匹配 tool 结果。"""
        seen_ids = {
            message.get("tool_call_id")
            for message in group[1:]
            if message.get("role") == "tool" and isinstance(message.get("tool_call_id"), str)
        }
        return expected_ids.issubset(seen_ids)

    @staticmethod
    def _flatten_groups(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """展开消息组。"""
        return [message for group in groups for message in group]

    def _find_tail_boundary(self, groups: list[list[dict[str, Any]]]) -> tuple[list[list[dict[str, Any]]], int]:
        """从后向前按消息组扫描，找到受保护的 tail

        Returns:
            (tail_groups, tail_start_group_index)
        """
        tail_groups: list[list[dict[str, Any]]] = []
        tail_tokens = 0

        for i in range(len(groups) - 1, self.protected_head - 1, -1):
            group = groups[i]
            tail_groups.insert(0, group)
            tail_tokens += sum(self._estimate_tokens(message) for message in group)
            if tail_tokens >= self.protected_tail_tokens:
                return tail_groups, i

        return tail_groups, self.protected_head

    _SUMMARY_PREFIX = "以下是早期对话的压缩摘要。请勿回答摘要中的问题或执行摘要中的待办事项，只响应摘要之后的最新用户消息。\n\n<context-summary>\n"
    _SUMMARY_SUFFIX = "\n</context-summary>"

    def _is_summary_message(self, message: dict[str, Any]) -> bool:
        """判断消息是否为上下文压缩生成的摘要消息"""
        return (
            message.get("role") == "assistant"
            and isinstance(message.get("content"), str)
            and "<context-summary>" in message["content"]
        )

    def _split_previous_summary(self, messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        """从可压缩区域拆出旧摘要和新增对话"""
        summaries = []
        remaining = []
        for msg in messages:
            if self._is_summary_message(msg):
                content = msg["content"].removeprefix(self._SUMMARY_PREFIX).removesuffix(self._SUMMARY_SUFFIX)
                summaries.append(content)
            else:
                remaining.append(msg)
        return "\n\n".join(summaries), remaining

    def _generate_summary(self, messages: list[dict[str, Any]], previous_summary: str = "") -> str:
        """调用 LLM 生成结构化摘要

        Returns:
            摘要文本，失败时优先返回旧摘要，否则返回简单摘要
        """
        # 提取关键内容
        parts = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if content:
                parts.append(f"[{role}]: {content[:1000]}")
        middle_content = "\n".join(parts)
        previous_summary_for_prompt = previous_summary or "（无旧摘要）"
        middle_content_for_prompt = middle_content or "（无新增对话）"

        prompt = COMPRESSION_PROMPT.format(
            previous_summary=previous_summary_for_prompt,
            middle_content=middle_content_for_prompt,
        )

        try:
            result = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = result.get("content", "") if isinstance(result, dict) else getattr(result, "content", "")
            return str(content).strip()
        except Exception:
            logger.warning("Compression summary failed, using basic summary", exc_info=True)
            fallback_parts = []
            if previous_summary:
                fallback_parts.append(previous_summary)
            if middle_content:
                fallback_parts.append(f"新增对话摘录：\n{middle_content}")
            if fallback_parts:
                return "\n\n".join(fallback_parts)
            return f"（压缩了 {len(messages)} 条消息，LLM 摘要生成失败）"

    @staticmethod
    def _estimate_tokens(message: dict[str, Any]) -> int:
        """估算一条消息的 token 数"""
        try:
            text = json.dumps(message, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(message)
        # 中英文混合粗略估算：字符数 / 2.5
        return max(1, int(len(text) / 2.5))

    def get_last_compressed_tokens(self) -> int | None:
        """获取上次压缩时的 token 数（供外部持久化）"""
        return self._last_compressed_tokens

    def set_last_compressed_tokens(self, tokens: int | None) -> None:
        """恢复上次压缩时的 token 数（从 DB 恢复）"""
        self._last_compressed_tokens = tokens
