"""loader 扫描与索引构建测试"""

import tempfile
from pathlib import Path

from skills.loader import scan_skills, build_index, load_skill, get_skills_prompt, SkillIndex


def _make_skill(root: Path, category: str, name: str, description="A test skill"):
    skill_dir = root / category / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"""---
name: {name}
description: "{description}"
category: {category}
---
# {name}
Body text.
""", encoding="utf-8")
    return skill_dir


class TestScanSkills:
    def test_scan_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_skills(tmp)
            assert result == []

    def test_scan_skills_in_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_skill(root, "dev", "python-testing")
            _make_skill(root, "data", "data-analysis")
            (root / "empty-category").mkdir()

            result = scan_skills(root)
            assert len(result) == 2
            paths = [p for p in result]
            assert any("python-testing/SKILL.md" in p for p in paths)
            assert any("data-analysis/SKILL.md" in p for p in paths)

    def test_ignore_directories_without_skill_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dev" / "no-skill").mkdir(parents=True)

            result = scan_skills(root)
            assert result == []


class TestBuildIndex:
    def test_build_index_from_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_skill(root, "dev", "python-testing", "Use for Python tests")
            _make_skill(root, "data", "data-analysis", "Use for data work")

            index = build_index(str(root))
            assert len(index) == 2
            names = [e.name for e in index]
            assert "python-testing" in names
            assert "data-analysis" in names

    def test_build_index_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = build_index(tmp)
            assert index == []


class TestLoadSkill:
    def test_load_skill_returns_meta_and_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_skill(root, "dev", "test-skill")
            path = str(root / "dev" / "test-skill" / "SKILL.md")

            skill = load_skill(path)
            assert skill is not None
            assert skill.name == "test-skill"
            assert skill.category == "dev"
            assert "Body text." in skill.body

    def test_load_skill_file_not_found(self):
        skill = load_skill("/nonexistent/SKILL.md")
        assert skill is None


class TestGetSkillsPrompt:
    def test_format_empty_index(self):
        result = get_skills_prompt([])
        assert "暂无可用技能" in result

    def test_format_grouped_by_category(self):
        entries = [
            SkillIndex(name="py-test", description="Python testing", category="dev", path="/tmp/py-test"),
            SkillIndex(name="data-sql", description="SQL queries", category="data", path="/tmp/data-sql"),
            SkillIndex(name="git-flow", description="Git workflow", category="dev", path="/tmp/git-flow"),
        ]
        result = get_skills_prompt(entries)
        assert "## dev" in result
        assert "## data" in result
        assert "py-test" in result
        assert "data-sql" in result
        assert "git-flow" in result