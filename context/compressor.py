"""上下文压缩：工具结果裁剪 + LLM 结构化摘要 + 头尾保护"""

import json
import logging
from typing import Any

from llm.client import LLMClient

logger = logging.getLogger(__name__)

COMPRESSION_PROMPT = """请总结以下对话的中间部分，用简洁的中文描述。

要求：
- 只总结关键信息，不编造不存在的细节
- 用以下格式输出（每个字段一行或多行）：

当前任务：
已完成：
进行中：
关键决策：
待解决问题：
相关文件：
剩余工作：

以下是需要总结的对话内容：
{middle_content}"""


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

        # 反抖动：上次压缩节省不到 10% 则跳过
        if self._last_compressed_tokens:
            saving_ratio = 1.0 - (current_tokens / self._last_compressed_tokens)
            if saving_ratio < self.min_saving:
                logger.debug(
                    "Compression saving %.1f%% below %.1f%% threshold, skipping",
                    saving_ratio * 100,
                    self.min_saving * 100,
                )
                return messages

        # 划分 head / tail / middle
        head = messages[:self.protected_head]
        tail, tail_start = self._find_tail_boundary(messages)
        middle = messages[self.protected_head:tail_start]

        if not middle:
            logger.debug("No middle messages to compress")
            return messages

        # LLM 生成结构化摘要
        summary = self._generate_summary(middle)

        # 组装压缩结果
        summary_msg: dict[str, Any] = {
            "role": "assistant",
            "content": f"[对话摘要]\n{summary}",
        }
        compressed = head + [summary_msg] + tail

        self._last_compressed_tokens = current_tokens
        logger.info(
            "Compressed %d → %d messages (head=%d, summary=1, tail=%d)",
            total, len(compressed), len(head), len(tail),
        )
        return compressed

    def trim_tool_results(self, messages: list[dict[str, Any]], max_tokens: int = 500) -> list[dict[str, Any]]:
        """裁剪旧工具结果，将长结果替换为简短摘要

        Args:
            messages: 消息列表
            max_tokens: 工具结果保留的最大字符数

        Returns:
            裁剪后的消息列表
        """
        result = []
        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if len(content) > max_tokens:
                    trimmed = {
                        **msg,
                        "content": content[:max_tokens] + f"\n...[截断，原 {len(content)} 字符]",
                    }
                    result.append(trimmed)
                    continue
            result.append(msg)
        return result

    def _find_tail_boundary(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        """从后向前扫描，找到受保护的 tail

        Returns:
            (tail_messages, tail_start_index)
        """
        tail_messages = []
        tail_tokens = 0

        for i in range(len(messages) - 1, self.protected_head - 1, -1):
            msg = messages[i]
            tail_messages.insert(0, msg)
            tail_tokens += self._estimate_tokens(msg)
            if tail_tokens >= self.protected_tail_tokens:
                return tail_messages, i

        return tail_messages, self.protected_head

    def _generate_summary(self, messages: list[dict[str, Any]]) -> str:
        """调用 LLM 生成结构化摘要

        Returns:
            摘要文本，失败时返回简单摘要
        """
        # 提取关键内容
        parts = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if content:
                parts.append(f"[{role}]: {content[:500]}")
        middle_content = "\n".join(parts)

        prompt = COMPRESSION_PROMPT.format(middle_content=middle_content)

        try:
            result = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            return result.content.strip()
        except Exception:
            logger.warning("Compression summary failed, using basic summary", exc_info=True)
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
