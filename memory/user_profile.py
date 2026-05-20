"""用户建模：USER.md 读写 + LLM 驱动画像更新"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.client import LLMClient

logger = logging.getLogger(__name__)

MAX_PROFILE_LENGTH = 5000

PROFILE_UPDATE_PROMPT = """你正在维护一个用户的个人画像。根据新的观察更新画像，合并旧信息和新信息。

要求：
- 用中文输出，简洁清晰
- 保持画像总长度不超过 5000 字符
- 如果超出，压缩最旧的条目，保留最新的
- 包含：偏好、习惯、技能、项目上下文、常用工具

当前画像：
{current_profile}

新观察：
{observations}

请输出更新后的完整画像（仅输出画像内容，无需解释）："""


class UserProfileManager:
    """用户画像管理器，支持 LLM 驱动的画像更新"""

    def __init__(self, profile_path: str, llm: "LLMClient | None" = None):
        self.profile_path = Path(profile_path)
        self.llm = llm

    def read_profile(self) -> str:
        """读取用户画像

        Returns:
            USER.md 内容，不存在返回 ""
        """
        try:
            if self.profile_path.exists():
                return self.profile_path.read_text(encoding="utf-8")
        except Exception:
            logger.warning("Failed to read profile at %s", self.profile_path, exc_info=True)
        return ""

    def write_profile(self, content: str) -> None:
        """写入用户画像"""
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        # 截断超长内容
        if len(content) > MAX_PROFILE_LENGTH:
            content = content[:MAX_PROFILE_LENGTH]
        self.profile_path.write_text(content, encoding="utf-8")
        logger.info("Profile written to %s (%d chars)", self.profile_path, len(content))

    def update_profile(self, observations: str) -> str:
        """LLM 驱动的画像更新：合并当前画像与新观察

        Args:
            observations: 新的观察/信息

        Returns:
            更新后的画像内容，LLM 调用失败时返回原画像
        """
        current = self.read_profile()

        if not self.llm:
            # 无 LLM 时直接追加
            new_content = current + "\n" + observations if current else observations
            self.write_profile(new_content)
            return new_content

        prompt = PROFILE_UPDATE_PROMPT.format(
            current_profile=current or "(暂无画像)",
            observations=observations,
        )

        try:
            result = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            new_profile = result.content.strip()
            self.write_profile(new_profile)
            return new_profile
        except Exception:
            logger.warning("LLM profile update failed, preserving original", exc_info=True)
            return current
