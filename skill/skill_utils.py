"""技能工具模块 — frontmatter 解析、名称校验、目录定位。

供技能加载器和技能工具共用的基础函数：
- parse_frontmatter: 从 SKILL.md 内容中提取 YAML frontmatter
- validate_skill_name: 校验技能名称是否符合命名规则
- resolve_skill_dir: 按名称在根路径下查找技能目录
"""

import glob as glob_module
import re
from pathlib import Path

import yaml

# 匹配 YAML frontmatter（--- 分隔符），DOTALL 使 . 匹配换行符
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# 同时处理空的 frontmatter 块（"---\n---"）
_EMPTY_FRONTMATTER_RE = re.compile(r"^---\s*\n---\s*\n")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 SKILL.md 中的 YAML frontmatter。

    返回 (meta_dict, body_text)。无 frontmatter 或 YAML 解析失败时返回 ({}, 原文)。
    """
    # 优先匹配空 frontmatter 块（---\n---）
    match = _EMPTY_FRONTMATTER_RE.match(content)
    if match:
        body = content[match.end():]
        return {}, body

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    yaml_str = match.group(1).strip()
    if not yaml_str:
        body = content[match.end():]
        return {}, body

    try:
        meta = yaml.safe_load(yaml_str)
    except yaml.YAMLError:
        return {}, content

    # safe_load 可能对空 YAML 返回 None，对标量/列表返回非 dict
    if not isinstance(meta, dict):
        return {}, content[match.end():]

    body = content[match.end():]
    return meta, body


def validate_skill_name(name: str) -> str | None:
    """校验技能名称的合法性。

    规则：
    - 仅允许字母、数字、连字符和下划线
    - 最长 64 字符
    - 不能为空

    合法返回 None，非法返回错误描述字符串。
    """
    if not name:
        return "技能名称不能为空"

    if len(name) > 64:
        return f"技能名称最多 64 个字符（当前 {len(name)} 个）"

    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        return "技能名称只能包含字母、数字、连字符和下划线"

    return None


def resolve_skill_dir(root: str, name: str) -> str | None:
    """遍历 root/{category}/{name}/ 目录结构，返回第一个按名称匹配且包含
    SKILL.md 的目录路径。

    返回字符串格式的目录路径，未找到则返回 None。
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return None

    escaped_name = glob_module.escape(name)
    for skill_dir in sorted(root_path.glob("*/" + escaped_name)):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        # 找到匹配目录且包含 SKILL.md
        return str(skill_dir)

    return None