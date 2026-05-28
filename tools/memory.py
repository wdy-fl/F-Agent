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

    elif action == "read_memory":
        if not _memory_manager:
            return json.dumps({"error": "Memory manager not available"}, ensure_ascii=False)
        content = _memory_manager.get_memory()
        return json.dumps({"content": content}, ensure_ascii=False)

    elif action == "append_memory":
        content = args.get("content", "")
        if not content:
            return json.dumps({"error": "content is required for append_memory action"}, ensure_ascii=False)
        if not _memory_manager:
            return json.dumps({"error": "Memory manager not available"}, ensure_ascii=False)
        _memory_manager.append_to_memory(content)
        return json.dumps({"status": "appended"}, ensure_ascii=False)

    elif action == "read_soul":
        if not _memory_manager:
            return json.dumps({"error": "Memory manager not available"}, ensure_ascii=False)
        content = _memory_manager.get_soul()
        return json.dumps({"content": content}, ensure_ascii=False)

    elif action == "update_soul":
        content = args.get("content", "")
        if not content:
            return json.dumps({"error": "content is required for update_soul action"}, ensure_ascii=False)
        if not _memory_manager:
            return json.dumps({"error": "Memory manager not available"}, ensure_ascii=False)
        _memory_manager.update_soul(content)
        return json.dumps({"status": "updated"}, ensure_ascii=False)

    elif action == "read_agent":
        if not _memory_manager:
            return json.dumps({"error": "Memory manager not available"}, ensure_ascii=False)
        content = _memory_manager.get_agent()
        return json.dumps({"content": content}, ensure_ascii=False)

    elif action == "update_agent":
        content = args.get("content", "")
        if not content:
            return json.dumps({"error": "content is required for update_agent action"}, ensure_ascii=False)
        if not _memory_manager:
            return json.dumps({"error": "Memory manager not available"}, ensure_ascii=False)
        _memory_manager.update_agent(content)
        return json.dumps({"status": "updated"}, ensure_ascii=False)

    else:
        return json.dumps({
            "error": f"Unknown action: {action}",
            "available_actions": ["search", "save", "update_profile", "read_memory", "append_memory", "read_soul", "update_soul", "read_agent", "update_agent"],
        }, ensure_ascii=False)


registry.register(
    name="memory",
    schema={
        "type": "function",
        "function": {
            "name": "memory",
            "description": "管理持久化记忆和工作区文件。search=搜索历史对话，save=覆写用户画像，update_profile=LLM合并画像，read_memory/append_memory=读写Agent笔记，read_soul/update_soul=读写身份描述，read_agent/update_agent=读写行为指引",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作类型",
                        "enum": ["search", "save", "update_profile", "read_memory", "append_memory", "read_soul", "update_soul", "read_agent", "update_agent"],
                    },
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（action=search 时必填）",
                    },
                    "content": {
                        "type": "string",
                        "description": "内容（action=save/append_memory/update_soul/update_agent 时必填）",
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
