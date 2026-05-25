"""技能扫描与索引构建模块。

提供技能目录扫描、SKILL.md 解析、内存索引构建和系统提示词注入格式化功能。
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from skills.skill_utils import parse_frontmatter

import logging

logger = logging.getLogger(__name__)


@dataclass
class SkillIndex:
    """单个技能的索引条目。

    Attributes:
        name: 技能名称（来自 frontmatter）
        description: 技能描述（来自 frontmatter）
        category: 技能分类（来自 frontmatter）
        path: SKILL.md 文件的绝对路径
        body: SKILL.md 正文（不含 frontmatter），load_skill 时填充
    """
    name: str
    description: str
    category: str
    path: str
    body: str = ""


def scan_skills(root: str) -> list[str]:
    """扫描根目录下所有 SKILL.md 文件路径。

    递归遍历 root/{category}/{name}/ 目录结构，返回所有 SKILL.md 的绝对路径列表，
    按路径排序以保证确定性结果。

    Args:
        root: 技能目录的根路径（包含按 category 分组的子目录）

    Returns:
        所有 SKILL.md 文件的绝对路径列表。如果 root 不存在或不是目录，返回空列表。
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    return sorted(str(p) for p in root_path.rglob("SKILL.md") if p.is_file())


def build_index(root: str) -> list[SkillIndex]:
    """扫描技能并构建内存索引。

    对每个 SKILL.md 解析 frontmatter 提取元数据，但不加载正文以节省内存。
    扫描或解析失败的文件会被静默跳过。

    Args:
        root: 技能目录的根路径

    Returns:
        SkillIndex 列表（不含 body），按扫描路径顺序排列。
    """
    paths = scan_skills(root)
    index: list[SkillIndex] = []
    for path in paths:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        meta, _body = parse_frontmatter(content)
        name = meta.get("name")
        if not name:
            logger.warning("技能文件缺少 name 字段，已跳过: %s", path)
            continue
        category = str(meta.get("category", ""))
        if not category:
            logger.warning("技能文件缺少 category 字段: %s", path)
        index.append(SkillIndex(
            name=str(name),
            description=str(meta.get("description", "")),
            category=category,
            path=path,
        ))
    return index


def load_skill(path: str) -> SkillIndex | None:
    """读取单个 SKILL.md 并解析完整内容。

    返回包含正文的 SkillIndex。如果文件无法读取或 frontmatter 中缺少 name，返回 None。

    Args:
        path: SKILL.md 文件的路径

    Returns:
        完整的 SkillIndex（含 body），或 None（文件不可读/无 name）
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    meta, body = parse_frontmatter(content)
    name = meta.get("name")
    if not name:
        return None
    return SkillIndex(
        name=str(name),
        description=str(meta.get("description", "")),
        category=str(meta.get("category", "")),
        path=path,
        body=body,
    )


def get_skills_prompt(index: list[SkillIndex]) -> str:
    """将技能索引格式化为系统提示词注入文本。

    按 category 分组，生成 <available_skills> 块以供注入到系统提示词中。

    Args:
        index: build_index 返回的技能索引列表

    Returns:
        格式化的可用技能提示词文本。空索引时返回 "(暂无可用技能)"。
    """
    if not index:
        return "<available_skills>\n(暂无可用技能)\n</available_skills>"

    by_category: dict[str, list[SkillIndex]] = defaultdict(list)
    for entry in index:
        if entry.category:
            by_category[entry.category].append(entry)

    lines = ["<available_skills>"]
    for category, entries in sorted(by_category.items()):
        lines.append(f"## {category}")
        for entry in entries:
            lines.append(f"- {entry.name}: {entry.description}")
    lines.append("</available_skills>")
    return "\n".join(lines)