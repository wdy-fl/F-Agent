"""记忆工具：供 LLM 调用的记忆读写和画像更新入口"""

import json
import logging
from typing import TYPE_CHECKING

from tools.registry import registry

if TYPE_CHECKING:
    from memory.manager import MemoryManager
    from memory.user_profile import UserProfileManager

logger = logging.getLogger(__name__)

_memory_manager: "MemoryManager | None" = None
_profile_manager: "UserProfileManager | None" = None


def set_managers(
    memory_manager: "MemoryManager | None" = None,
    profile_manager: "UserProfileManager | None" = None,
) -> None:
    """注入记忆管理器引用，在 CLI 初始化时调用"""
    global _memory_manager, _profile_manager
    _memory_manager = memory_manager
    _profile_manager = profile_manager


def handle_memory(args: dict) -> str:
    """memory 工具处理函数

    Actions:
        search: FTS5 全文搜索历史消息
        save: 写入用户画像
        update_profile: LLM 驱动的画像更新
    """
    action = args.get("action", "")

    if action == "search":
        query = args.get("query", "")
        limit = args.get("limit", 5)
        if not query:
            return json.dumps({"error": "query is required for search action"}, ensure_ascii=False)
        if not _memory_manager:
            return json.dumps({"error": "Memory manager not available"}, ensure_ascii=False)
        results = _memory_manager.session_db.search_messages(query, limit=limit)
        return json.dumps(results, ensure_ascii=False, default=str)

    elif action == "save":
        content = args.get("content", "")
        if not content:
            return json.dumps({"error": "content is required for save action"}, ensure_ascii=False)
        if not _memory_manager:
            return json.dumps({"error": "Memory manager not available"}, ensure_ascii=False)
        _memory_manager.update_user_profile(content)
        return json.dumps({"status": "saved"}, ensure_ascii=False)

    elif action == "update_profile":
        observations = args.get("observations", "")
        if not observations:
            return json.dumps({"error": "observations is required for update_profile action"}, ensure_ascii=False)
        if not _profile_manager:
            return json.dumps({"error": "Profile manager not available"}, ensure_ascii=False)
        new_profile = _profile_manager.update_profile(observations)
        return json.dumps({"status": "updated", "profile_length": len(new_profile)}, ensure_ascii=False)

    else:
        return json.dumps({
            "error": f"Unknown action: {action}",
            "available_actions": ["search", "save", "update_profile"],
        }, ensure_ascii=False)


registry.register(
    name="memory",
    schema={
        "type": "function",
        "function": {
            "name": "memory",
            "description": "管理记忆和用户画像。action='search' 搜索历史对话，'save' 写入画像，'update_profile' 让 LLM 合并新观察到画像",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作类型：search（搜索历史）、save（写入画像）、update_profile（LLM 合并画像）",
                        "enum": ["search", "save", "update_profile"],
                    },
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（action=search 时必填）",
                    },
                    "content": {
                        "type": "string",
                        "description": "画像内容（action=save 时必填）",
                    },
                    "observations": {
                        "type": "string",
                        "description": "新观察信息（action=update_profile 时必填）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "搜索结果数量上限，默认 5",
                        "default": 5,
                    },
                },
                "required": ["action"],
            },
        },
    },
    handler=handle_memory,
    parallel_safe=False,
)
