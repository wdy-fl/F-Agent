"""系统提示词构建：身份 + 技能索引 + 上下文文件"""

from datetime import datetime

from tools.registry import registry


def build_skills_section(skills_dir: str) -> str:
    """构建技能索引提示词段落"""
    from skill.loader import build_index, get_skills_prompt
    index = build_index(skills_dir)
    return get_skills_prompt(index)


def build_system_prompt(
    include_tools: bool = False,
    include_memory_guidance: bool = True,
    include_skills: bool = False,
    skills_dir: str = "",
    user_profile_path: str = "",
    soul_path: str = "",
    agent_guidance_path: str = "",
) -> str:
    """构建系统提示词

    Args:
        include_tools: 是否包含工具使用指引
        include_memory_guidance: 是否包含记忆系统指引
        include_skills: 是否包含技能系统指引和索引
        skills_dir: 技能目录路径
        user_profile_path: 用户画像文件路径（workspace/USER.md）
        soul_path: Agent 画像文件路径（workspace/SOUL.md）
        agent_guidance_path: Agent 指引文件路径（workspace/AGENT.md）
    """
    identity = _read_file(soul_path) if soul_path else _default_identity()
    parts = [identity]

    if user_profile_path:
        profile = _read_file(user_profile_path)
        if profile:
            parts.append(f"## 用户画像\n{profile}")

    if include_tools or include_memory_guidance or include_skills:
        guidance = _read_file(agent_guidance_path) if agent_guidance_path else ""
        if guidance:
            tool_index = _build_tool_index() if include_tools else "（暂无可用工具）"
            parts.append(guidance.format(tool_index=tool_index))

    if include_skills and skills_dir:
        parts.append(build_skills_section(skills_dir))

    # 时间戳
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts.append(f"\n当前时间：{now}")

    return "\n".join(parts)


def _read_file(path: str) -> str:
    """读取文件内容"""
    from pathlib import Path
    p = Path(path)
    try:
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _default_identity() -> str:
    """SOUL.md 不存在时的兜底身份描述"""
    return "你是阿福（F-Agent），一个智能个人助手。"


def _build_tool_index() -> str:
    """构建工具索引列表"""
    definitions = registry.get_definitions()
    if not definitions:
        return "（暂无可用工具）"

    lines = []
    for defn in definitions:
        func = defn.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        lines.append(f"- **{name}**: {desc}")
    return "\n".join(lines)
