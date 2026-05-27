"""记忆管理器：prefetch + sync + 用户画像读写"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from db.session import SessionDB

if TYPE_CHECKING:
    from llm.client import LLMClient

logger = logging.getLogger(__name__)


class MemoryManager:
    """记忆管理器，协调记忆预取、同步和用户画像"""

    def __init__(
        self,
        session_db: SessionDB,
        user_profile_path: str,
        llm: "LLMClient | None" = None,
    ):
        self.session_db = session_db
        self.user_profile_path = Path(user_profile_path)
        self.llm = llm

    def prefetch(self, user_message: str, limit: int = 5) -> str:
        """预取相关历史记忆，返回拼装好的记忆上下文字符串

        Args:
            user_message: 当前用户输入，用作搜索关键词
            limit: FTS5 搜索最大返回条数

        Returns:
            拼装好的记忆上下文，格式为：
            [历史记忆]
            <FTS5 搜索结果>
        """
        parts = []

        # FTS5 搜索相关历史消息
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

    def sync(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        """同步记忆（FTS5 索引由触发器自动维护，此处为扩展钩子）

        Args:
            session_id: 当前会话 ID
            user_msg: 用户消息
            assistant_msg: 助手回复
        """
        logger.debug("MemoryManager.sync called for session %s", session_id)

    def get_user_profile(self) -> str:
        """读取 USER.md 用户画像

        Returns:
            用户画像内容，文件不存在时返回空字符串
        """
        try:
            if self.user_profile_path.exists():
                return self.user_profile_path.read_text(encoding="utf-8")
        except Exception:
            logger.warning("Failed to read user profile", exc_info=True)
        return ""

    def update_user_profile(self, new_content: str) -> None:
        """写入 USER.md 用户画像

        Args:
            new_content: 新的用户画像内容
        """
        self.user_profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_profile_path.write_text(new_content, encoding="utf-8")
        logger.info("User profile updated at %s", self.user_profile_path)
