"""技能管理工具：供 LLM 调用 skills_list/skill_view/skill_manage"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from skill.loader import build_index, load_skill
from skill.skill_utils import parse_frontmatter, resolve_skill_dir, validate_skill_name
from tools.registry import registry

logger = logging.getLogger(__name__)

_skills_dir: Path | None = None


def set_skills_dir(path: Path | None) -> None:
    """注入技能目录路径，在 AgentLoop 初始化时调用"""
    global _skills_dir
    _skills_dir = path


def _check_dir() -> str | None:
    if _skills_dir is None:
        return json.dumps({"error": "技能目录未配置"}, ensure_ascii=False)
    return None


def handle_skills_list(args: dict[str, Any]) -> str:
    """列出所有可用技能（name + description + category）"""
    err = _check_dir()
    if err:
        return err

    index = build_index(str(_skills_dir))
    result = [{"name": e.name, "description": e.description, "category": e.category} for e in index]
    return json.dumps(result, ensure_ascii=False)


def handle_skill_view(args: dict[str, Any]) -> str:
    """加载技能的完整 SKILL.md 正文或关联文件"""
    err = _check_dir()
    if err:
        return err

    name = args.get("name", "")
    if not name:
        return json.dumps({"error": "name is required"}, ensure_ascii=False)

    file_path = args.get("file_path")
    if file_path:
        skill_dir = resolve_skill_dir(str(_skills_dir), name)
        if not skill_dir:
            return json.dumps({"error": f"技能不存在: {name}"}, ensure_ascii=False)
        full_path = os.path.normpath(os.path.join(skill_dir, file_path))
        if not full_path.startswith(skill_dir):
            return json.dumps({"error": "file_path 不得访问技能目录外部"}, ensure_ascii=False)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return json.dumps({"body": f.read(), "path": file_path, "skill": name}, ensure_ascii=False)
        except (OSError, UnicodeDecodeError) as e:
            return json.dumps({"error": f"读取文件失败: {e}"}, ensure_ascii=False)

    skill_dir = resolve_skill_dir(str(_skills_dir), name)
    if not skill_dir:
        return json.dumps({"error": f"技能不存在: {name}"}, ensure_ascii=False)

    skill = load_skill(os.path.join(skill_dir, "SKILL.md"))
    if not skill:
        return json.dumps({"error": f"加载技能失败: {name}"}, ensure_ascii=False)

    return json.dumps({"body": skill.body, "name": skill.name, "category": skill.category}, ensure_ascii=False)


def _insert_date_into_frontmatter(content: str, key: str, value: str) -> str:
    """在 frontmatter 的 opening --- 之后插入一个日期字段。

    只操作第一个 --- 块（frontmatter opening delimiter），
    不会误命中 closing ---。
    """
    if key in content:
        return content
    idx = content.find("---\n")
    if idx == -1:
        return content
    insert_pos = idx + len("---\n")
    return content[:insert_pos] + f"{key}: {value}\n" + content[insert_pos:]


def handle_skill_manage(args: dict[str, Any]) -> str:
    """创建/编辑/删除技能或关联文件"""
    err = _check_dir()
    if err:
        return err

    action = args.get("action", "")
    name = args.get("name", "")

    if action not in ("create", "edit", "delete", "write_file", "remove_file"):
        return json.dumps({
            "error": f"未知 action: {action}",
            "available_actions": ["create", "edit", "delete", "write_file", "remove_file"],
        }, ensure_ascii=False)

    if not name:
        return json.dumps({"error": "name is required"}, ensure_ascii=False)

    if action == "delete":
        skill_dir = resolve_skill_dir(str(_skills_dir), name)
        if not skill_dir:
            return json.dumps({"error": f"技能不存在: {name}"}, ensure_ascii=False)
        shutil.rmtree(skill_dir)
        logger.info("技能已删除: %s (%s)", name, skill_dir)
        return json.dumps({"status": "deleted", "name": name, "note": "重启会话后生效"}, ensure_ascii=False)

    if action == "create":
        val_err = validate_skill_name(name)
        if val_err:
            return json.dumps({"error": val_err}, ensure_ascii=False)

        existing = resolve_skill_dir(str(_skills_dir), name)
        if existing:
            return json.dumps({"error": f"技能已存在: {name}"}, ensure_ascii=False)

        content = args.get("content", "")
        if not content:
            return json.dumps({"error": "content is required for create"}, ensure_ascii=False)

        meta, _body = parse_frontmatter(content)
        category = meta.get("category", "uncategorized")
        now = datetime.now().strftime("%Y-%m-%d")

        # Safely insert date fields only into the opening frontmatter block
        content = _insert_date_into_frontmatter(content, "created_at", now)
        content = _insert_date_into_frontmatter(content, "updated_at", now)

        skill_dir = _skills_dir / category / name
        skill_dir.mkdir(parents=True, exist_ok=False)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        logger.info("技能已创建: %s (%s)", name, skill_dir)
        return json.dumps({"status": "created", "name": name, "path": str(skill_dir), "note": "重启会话后生效"}, ensure_ascii=False)

    if action == "edit":
        content = args.get("content", "")
        if not content:
            return json.dumps({"error": "content is required for edit"}, ensure_ascii=False)

        skill_dir = resolve_skill_dir(str(_skills_dir), name)
        if not skill_dir:
            return json.dumps({"error": f"技能不存在: {name}"}, ensure_ascii=False)

        skill_md = os.path.join(skill_dir, "SKILL.md")
        Path(skill_md).write_text(content, encoding="utf-8")
        logger.info("技能已更新: %s", name)
        return json.dumps({"status": "updated", "name": name, "note": "重启会话后生效"}, ensure_ascii=False)

    if action == "write_file":
        content = args.get("content", "")
        if not content:
            return json.dumps({"error": "content is required for write_file"}, ensure_ascii=False)

        skill_dir = resolve_skill_dir(str(_skills_dir), name)
        if not skill_dir:
            return json.dumps({"error": f"技能不存在: {name}"}, ensure_ascii=False)

        refs_dir = Path(skill_dir) / "references"
        refs_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_name = f"note-{timestamp}.md"
        (refs_dir / file_name).write_text(content, encoding="utf-8")
        logger.info("关联文件已写入: %s/%s", name, file_name)
        return json.dumps({"status": "file_written", "name": name, "path": f"references/{file_name}", "note": "重启会话后生效"}, ensure_ascii=False)

    if action == "remove_file":
        file_path = args.get("content", "")
        if not file_path:
            return json.dumps({"error": "content (file_path) is required for remove_file"}, ensure_ascii=False)

        skill_dir = resolve_skill_dir(str(_skills_dir), name)
        if not skill_dir:
            return json.dumps({"error": f"技能不存在: {name}"}, ensure_ascii=False)

        full_path = os.path.normpath(os.path.join(skill_dir, file_path))
        if not full_path.startswith(skill_dir):
            return json.dumps({"error": "file_path 不得访问技能目录外部"}, ensure_ascii=False)

        try:
            os.remove(full_path)
            logger.info("关联文件已删除: %s/%s", name, file_path)
            return json.dumps({"status": "file_removed", "name": name, "path": file_path, "note": "重启会话后生效"}, ensure_ascii=False)
        except OSError as e:
            return json.dumps({"error": f"删除文件失败: {e}"}, ensure_ascii=False)


# Register tools on global registry

registry.register(
    name="skills_list",
    schema={
        "type": "function",
        "function": {
            "name": "skills_list",
            "description": "列出所有可用技能的名称和描述。回复前先检查是否有相关技能可用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    handler=handle_skills_list,
    parallel_safe=True,
)

registry.register(
    name="skill_view",
    schema={
        "type": "function",
        "function": {
            "name": "skill_view",
            "description": "加载技能的完整 SKILL.md 指令内容或关联文件。技能是程序性记忆，存储了完成特定任务的方法和流程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "要加载的技能名称"},
                    "file_path": {"type": "string", "description": "可选：技能目录下的关联文件相对路径，如 references/note.md"},
                },
                "required": ["name"],
            },
        },
    },
    handler=handle_skill_view,
    parallel_safe=True,
)

registry.register(
    name="skill_manage",
    schema={
        "type": "function",
        "function": {
            "name": "skill_manage",
            "description": (
                "管理技能（程序性记忆）。创建技能用于保存经过验证的工作流程和方法，供将来复用。"
                "create 用于创建新的技能，edit 用于完整替换现有技能内容，delete 用于删除技能，"
                "write_file 用于在技能下添加关联文件，remove_file 用于删除关联文件。"
                "何时创建技能：完成复杂任务（5+ 次工具调用）、克服棘手错误并找到解决方案后、"
                "用户纠正过的做法最终生效后、发现非平凡的工作流程后、或用户要求记住某个方法时。"
                "创建/删除前必须征求用户确认。使用技能时发现内容过时、不完整或错误，用 edit 修正。"
                "技能变更后需重启会话才能生效。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作类型：create（创建新技能）、edit（替换技能内容）、delete（删除技能）、write_file（添加关联文件）、remove_file（删除关联文件）",
                        "enum": ["create", "edit", "delete", "write_file", "remove_file"],
                    },
                    "name": {"type": "string", "description": "目标技能名称（必需）"},
                    "content": {
                        "type": "string",
                        "description": "create/edit/write_file/remove_file 时的内容。create/edit 时为完整的 SKILL.md 文本（含 frontmatter），write_file 时为文件内容，remove_file 时为要删除的文件相对路径",
                    },
                },
                "required": ["action", "name"],
            },
        },
    },
    handler=handle_skill_manage,
    parallel_safe=False,
)