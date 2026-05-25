"""Skill utilities — frontmatter parsing, name validation, and directory resolution.

Provides shared utilities used by the skills loader and skill tools:
- parse_frontmatter: Extract YAML frontmatter from SKILL.md content
- validate_skill_name: Check skill name follows naming rules
- resolve_skill_dir: Locate a skill directory by name under a root path
"""

import glob as glob_module
import re
from pathlib import Path

import yaml

# Regex to match YAML frontmatter delimited by ---
# Uses DOTALL so . matches newlines within the frontmatter block
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Also handle empty frontmatter blocks: "---\n---"
_EMPTY_FRONTMATTER_RE = re.compile(r"^---\s*\n---\s*\n")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a SKILL.md string.

    Returns (meta_dict, body_text). If no frontmatter is found or the YAML
    can't be parsed, returns ({}, content).
    """
    # Check for empty frontmatter block first (---\n---)
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

    # safe_load may return None for empty YAML, or non-dict for scalar/list
    if not isinstance(meta, dict):
        return {}, content[match.end():]

    body = content[match.end():]
    return meta, body


def validate_skill_name(name: str) -> str | None:
    """Validate a skill name.

    Rules:
    - Only alphanumeric characters, hyphens, and underscores
    - Maximum 64 characters
    - Must not be empty

    Returns None if valid, or an error string describing the problem.
    """
    if not name:
        return "Skill name must not be empty"

    if len(name) > 64:
        return f"Skill name must be at most 64 characters (got {len(name)})"

    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        return "Skill name must only contain alphanumeric characters, hyphens, and underscores"

    return None


def resolve_skill_dir(root: str, name: str) -> str | None:
    """Walk root/{category}/{name}/ directories and return the path to the
    first directory by name containing a SKILL.md file.

    Returns the directory path as a string, or None if not found.
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
        # Found a matching directory with SKILL.md
        return str(skill_dir)

    return None