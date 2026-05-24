"""skill_utils 单元测试"""

import tempfile
from pathlib import Path

from skills.skill_utils import parse_frontmatter, validate_skill_name, resolve_skill_dir


class TestParseFrontmatter:
    def test_parse_valid_frontmatter(self):
        content = """---
name: test-skill
description: "A test skill"
category: testing
---
# Skill Body
Some instructions.
"""
        meta, body = parse_frontmatter(content)
        assert meta["name"] == "test-skill"
        assert meta["description"] == "A test skill"
        assert meta["category"] == "testing"
        assert "# Skill Body" in body
        assert "Some instructions." in body

    def test_parse_no_frontmatter(self):
        content = "# Just a heading\nNo frontmatter here."
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_parse_empty_frontmatter(self):
        content = "---\n---\nBody text."
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == "Body text."

    def test_parse_frontmatter_with_tags(self):
        content = """---
name: py-test
description: "Test skill"
category: dev
tags: [python, testing]
---
Body.
"""
        meta, body = parse_frontmatter(content)
        assert meta["tags"] == ["python", "testing"]

    def test_parse_malformed_yaml(self):
        content = """---
name: [unclosed
---
Body.
"""
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == content


class TestValidateSkillName:
    def test_valid_names(self):
        assert validate_skill_name("python-testing") is None
        assert validate_skill_name("my_skill_123") is None
        assert validate_skill_name("a") is None

    def test_invalid_characters(self):
        err = validate_skill_name("hello world")
        assert err is not None

        err = validate_skill_name("skill/name")
        assert err is not None

        err = validate_skill_name("skill.name")
        assert err is not None

    def test_too_long(self):
        err = validate_skill_name("a" * 65)
        assert err is not None

    def test_empty(self):
        err = validate_skill_name("")
        assert err is not None


class TestResolveSkillDir:
    def test_resolve_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dev" / "test-skill").mkdir(parents=True)
            (root / "dev" / "test-skill" / "SKILL.md").touch()

            result = resolve_skill_dir(str(root), "test-skill")
            assert result == str(root / "dev" / "test-skill")

    def test_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_skill_dir(tmp, "nonexistent")
            assert result is None

    def test_duplicate_name_different_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cat-a" / "dup-name").mkdir(parents=True)
            (root / "cat-a" / "dup-name" / "SKILL.md").touch()
            (root / "cat-b" / "dup-name").mkdir(parents=True)
            (root / "cat-b" / "dup-name" / "SKILL.md").touch()

            result = resolve_skill_dir(str(root), "dup-name")
            assert result is not None