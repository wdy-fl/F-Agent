"""记忆管理器：prefetch + sync + 四个持久化文件的 LLM 合并读写"""

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from db.session import SessionDB

if TYPE_CHECKING:
    from llm.client import LLMClient

logger = logging.getLogger(__name__)

MAX_PROFILE_LENGTH = 5000
MAX_MEMORY_LENGTH = 10000

PROFILE_MERGE_PROMPT = """你正在维护一个用户的个人画像。根据新的观察更新画像，合并旧信息和新信息。

要求：
- 用中文输出，简洁清晰
- 保持画像总长度不超过 5000 字符
- 如果超出，压缩最旧的条目，保留最新的
- 包含：偏好、习惯、技能、项目上下文、常用工具

当前画像：
{current_content}

新观察：
{observations}

请输出更新后的完整画像（仅输出画像内容，无需解释）："""

SOUL_MERGE_PROMPT = """你正在维护一个 Agent 的身份描述（SOUL.md）。根据新的观察更新身份描述。

要求：
- 用中文输出，简洁清晰
- 保留核心身份和能力描述
- 合并新的行为准则或调整

当前身份描述：
{current_content}

调整内容：
{observations}

请输出更新后的完整身份描述（仅输出内容，无需解释）："""

AGENT_MERGE_PROMPT = """你正在维护一个 Agent 的行为指引（AGENT.md）。根据新的观察更新行为指引。

要求：
- 用中文输出，简洁清晰
- 保留工具使用规则、记忆系统、技能系统等核心章节结构
- 合并新的指引内容

当前行为指引：
{current_content}

调整内容：
{observations}

请输出更新后的完整行为指引（仅输出内容，无需解释）："""

MEMORY_CONSOLIDATE_PROMPT = """你正在整理 Agent 的持久化笔记（MEMORY.md）。对以下条目做去重、合并、裁剪。
要求：
- 用中文输出，简洁清晰
- 保留最重要的信息，去除重复和过时内容
- 按时间倒序排列

当前笔记：
{current_content}

请输出整理后的笔记（仅输出内容，无需解释）："""


class MemoryManager:
    """记忆管理器，统一管理四个持久化文件的读写和 LLM 合并"""

    def __init__(
        self,
        session_db: SessionDB,
        user_profile_path: str,
        memory_path: str = "",
        soul_path: str = "",
        agent_path: str = "",
        llm: "LLMClient | None" = None,
    ):
        self.session_db = session_db
        self.user_profile_path = Path(user_profile_path)
        self.memory_path = Path(memory_path) if memory_path else None
        self.soul_path = Path(soul_path) if soul_path else None
        self.agent_path = Path(agent_path) if agent_path else None
        self.llm = llm

    # ---- prefetch ----

    def prefetch(self, user_message: str, limit: int = 5) -> str:
        """预取相关历史记忆，返回拼装好的记忆上下文字符串"""
        parts = []
        search_results = self.session_db.search_messages(user_message, limit=limit)
        if search_results:
            lines = ["[历史相关对话]"]
            for r in search_results:
                role = r.get("role", "unknown")
                content = r.get("content", "")
                if content:
                    lines.append(f"- [{role}]: {content[:200]}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    # ---- sync ----

    def sync(self, session_id: str, user_msg: str, assistant_msg: str) -> str | None:
        """每轮结束后判断是否有值得记住的新信息，返回精准 nudge 或 None"""
        if not self.llm:
            return None

        prompt = (
            "分析以下一轮对话，判断是否有值得持久化保存的新信息"
            "（用户偏好、项目约定、重要决策、新知识点等）。\n\n"
            f"用户：{user_msg[:500]}\n助手：{assistant_msg[:500]}\n\n"
            "如果有值得保存的信息，输出一行 JSON：\n"
            '{"has_info": true, "nudge": "精准提醒文本", "action": "update_profile|append_memory|update_soul|update_agent"}\n'
            "如果没有，输出：\n"
            '{"has_info": false}'
        )

        try:
            import json as _json
            result = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = result.get("content", "").strip()
            data = _json.loads(content)
            if data.get("has_info"):
                return data.get("nudge", "")
        except Exception:
            logger.debug("sync LLM judgment failed", exc_info=True)
        return None

    # ---- read methods ----

    def get_user_profile(self) -> str:
        return self._read_file(self.user_profile_path)

    def get_memory(self) -> str:
        return self._read_file(self.memory_path) if self.memory_path else ""

    def get_soul(self) -> str:
        return self._read_file(self.soul_path)

    def get_agent(self) -> str:
        return self._read_file(self.agent_path)

    # ---- write methods (all LLM-merged) ----

    def update_profile(self, observations: str) -> str:
        """LLM 合并更新 USER.md，返回更新后内容"""
        current = self.get_user_profile()
        new_content = self._llm_merge(
            PROFILE_MERGE_PROMPT, current, observations, MAX_PROFILE_LENGTH
        )
        self._write_file(self.user_profile_path, new_content)
        return new_content

    def update_soul(self, observations: str) -> str:
        """LLM 合并更新 SOUL.md，返回更新后内容"""
        current = self.get_soul()
        new_content = self._llm_merge(SOUL_MERGE_PROMPT, current, observations)
        self._write_file(self.soul_path, new_content)
        return new_content

    def update_agent(self, observations: str) -> str:
        """LLM 合并更新 AGENT.md，返回更新后内容"""
        current = self.get_agent()
        new_content = self._llm_merge(AGENT_MERGE_PROMPT, current, observations)
        self._write_file(self.agent_path, new_content)
        return new_content

    def append_to_memory(self, content: str) -> None:
        """追加条目到 MEMORY.md，带时间戳。超阈值时触发 LLM 整理。"""
        if not self.memory_path:
            return
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{timestamp}] {content}\n"
        with open(self.memory_path, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info("Memory appended at %s", self.memory_path)

        # 超阈值时触发 LLM 整理
        current = self.get_memory()
        if len(current) > MAX_MEMORY_LENGTH and self.llm:
            try:
                consolidated = self._llm_merge(
                    MEMORY_CONSOLIDATE_PROMPT, current, "", MAX_MEMORY_LENGTH
                )
                self._write_file(self.memory_path, consolidated)
                logger.info("Memory consolidated, %d -> %d chars", len(current), len(consolidated))
            except Exception:
                logger.warning("Memory consolidation failed", exc_info=True)

    # ---- internal ----

    def _llm_merge(
        self,
        prompt_template: str,
        current_content: str,
        observations: str,
        max_length: int | None = None,
    ) -> str:
        """LLM 合并：当前内容 + 新观察 → 更新后内容

        Args:
            prompt_template: 合并提示词模板，含 {current_content} 和 {observations} 占位符
            current_content: 当前文件内容
            observations: 新的观察/调整内容
            max_length: 可选，内容截断上限

        Returns:
            合并后的内容，LLM 失败时回退到直接追加
        """
        if not self.llm:
            return self._fallback_append(current_content, observations)

        prompt = prompt_template.format(
            current_content=current_content or "（暂无内容）",
            observations=observations,
        )

        try:
            result = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            new_content = result.get("content", "").strip()
        except Exception:
            logger.warning("LLM merge failed, using fallback", exc_info=True)
            return self._fallback_append(current_content, observations)

        if max_length and len(new_content) > max_length:
            new_content = new_content[:max_length]
        return new_content

    @staticmethod
    def _fallback_append(current: str, observations: str) -> str:
        """LLM 不可用时的退化方案：直接追加"""
        if current and observations:
            return current + "\n" + observations
        return observations or current

    @staticmethod
    def _read_file(path: Path | None) -> str:
        try:
            if path and path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            logger.warning("Failed to read file %s", path, exc_info=True)
        return ""

    @staticmethod
    def _write_file(path: Path | None, content: str) -> None:
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("File updated at %s", path)