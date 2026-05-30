"""skill 工具测试：注册 + handler 各 action"""

import json
import tempfile
from pathlib import Path

from tools.registry import registry
from tools.skill import handle_skills_list, handle_skill_view, handle_skill_manage, set_skills_dir


def _make_skill(root: Path, category: str, name: str, description="Test skill"):
    skill_dir = root / category / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"""---
name: {name}
description: "{description}"
category: {category}
created_at: 2026-05-24
updated_at: 2026-05-24
---
# {name}
## When to Use
Use this skill for testing.
## Instructions
Follow these steps.
""", encoding="utf-8")
    return skill_dir


def setup_skills_dir():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    _make_skill(root, "dev", "python-testing", "Python testing skill")
    _make_skill(root, "data", "data-analysis", "Data analysis skill")
    set_skills_dir(root)
    return tmp, root


class TestSkillsList:
    def test_list_returns_all_skills(self):
        tmp, root = setup_skills_dir()
        try:
            result = json.loads(handle_skills_list({}))
            assert len(result) == 2
            names = [s["name"] for s in result]
            assert "python-testing" in names
            assert "data-analysis" in names
        finally:
            tmp.cleanup()

    def test_list_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            set_skills_dir(Path(tmp))
            result = json.loads(handle_skills_list({}))
            assert result == []


class TestSkillView:
    def test_view_loads_body(self):
        tmp, root = setup_skills_dir()
        try:
            result = json.loads(handle_skill_view({"name": "python-testing"}))
            assert "# python-testing" in result["body"]
            assert "Follow these steps." in result["body"]
        finally:
            tmp.cleanup()

    def test_view_nonexistent_skill(self):
        tmp, root = setup_skills_dir()
        try:
            result = json.loads(handle_skill_view({"name": "nonexistent"}))
            assert "error" in result
        finally:
            tmp.cleanup()

    def test_view_no_name(self):
        result = json.loads(handle_skill_view({}))
        assert "error" in result

    def test_view_missing_manager(self):
        set_skills_dir(None)
        result = json.loads(handle_skill_view({"name": "test"}))
        assert "error" in result


class TestSkillManageCreate:
    def test_create_new_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_skills_dir(root)

            content = """---
name: new-skill
description: "A brand new skill"
category: dev
---
# new-skill
Instructions here.
"""
            result = json.loads(handle_skill_manage({
                "action": "create",
                "name": "new-skill",
                "content": content,
            }))
            assert result["status"] == "created"
            assert (root / "dev" / "new-skill" / "SKILL.md").is_file()

    def test_create_duplicate_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_skills_dir(root)
            _make_skill(root, "dev", "exist-skill")

            result = json.loads(handle_skill_manage({
                "action": "create",
                "name": "exist-skill",
                "content": "---\nname: exist-skill\ncategory: dev\n---\nBody.",
            }))
            assert "error" in result

    def test_create_invalid_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_skills_dir(root)

            result = json.loads(handle_skill_manage({
                "action": "create",
                "name": "bad name!",
                "content": "---\nname: bad name!\ncategory: dev\n---\nBody.",
            }))
            assert "error" in result

    def test_create_without_name_or_content(self):
        result = json.loads(handle_skill_manage({"action": "create"}))
        assert "error" in result

    def test_create_missing_manager(self):
        set_skills_dir(None)
        result = json.loads(handle_skill_manage({
            "action": "create",
            "name": "test",
            "content": "---\nname: test\ncategory: dev\n---\nBody.",
        }))
        assert "error" in result


class TestSkillManageEdit:
    def test_edit_existing_skill(self):
        tmp, root = setup_skills_dir()
        try:
            new_content = """---
name: python-testing
description: "Updated description"
category: dev
updated_at: 2026-05-25
---
# python-testing
New instructions.
"""
            result = json.loads(handle_skill_manage({
                "action": "edit",
                "name": "python-testing",
                "content": new_content,
            }))
            assert result["status"] == "updated"
            updated = (root / "dev" / "python-testing" / "SKILL.md").read_text()
            assert "New instructions." in updated
        finally:
            tmp.cleanup()

    def test_edit_nonexistent_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_skills_dir(root)

            result = json.loads(handle_skill_manage({
                "action": "edit",
                "name": "nonexistent",
                "content": "---\nname: nonexistent\ncategory: dev\n---\nBody.",
            }))
            assert "error" in result


class TestSkillManageDelete:
    def test_delete_existing_skill(self):
        tmp, root = setup_skills_dir()
        try:
            result = json.loads(handle_skill_manage({
                "action": "delete",
                "name": "python-testing",
            }))
            assert result["status"] == "deleted"
            assert not (root / "dev" / "python-testing").exists()
        finally:
            tmp.cleanup()

    def test_delete_nonexistent_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_skills_dir(root)

            result = json.loads(handle_skill_manage({
                "action": "delete",
                "name": "nonexistent",
            }))
            assert "error" in result


class TestSkillManageWriteFile:
    def test_write_file_under_skill(self):
        tmp, root = setup_skills_dir()
        try:
            result = json.loads(handle_skill_manage({
                "action": "write_file",
                "name": "python-testing",
                "content": "reference content",
            }))
            assert result["status"] == "file_written"
        finally:
            tmp.cleanup()


class TestSkillManageRemoveFile:
    def test_remove_file_under_skill(self):
        tmp, root = setup_skills_dir()
        try:
            ref_file = root / "dev" / "python-testing" / "references" / "test.txt"
            ref_file.parent.mkdir()
            ref_file.write_text("data")

            result = json.loads(handle_skill_manage({
                "action": "remove_file",
                "name": "python-testing",
                "content": "references/test.txt",
            }))
            assert result["status"] == "file_removed"
            assert not ref_file.exists()
        finally:
            tmp.cleanup()


class TestSkillManageUnknownAction:
    def test_unknown_action(self):
        result = json.loads(handle_skill_manage({"action": "unknown", "name": "x"}))
        assert "error" in result
        assert "available_actions" in result


class TestSkillToolsRegistered:
    def test_skills_list_registered(self):
        names = [d["function"]["name"] for d in registry.get_definitions()]
        assert "skills_list" in names
        assert "skill_view" in names
        assert "skill_manage" in names

    def test_skill_manage_description_includes_creation_contract(self):
        definition = next(
            d for d in registry.get_definitions()
            if d["function"]["name"] == "skill_manage"
        )
        description = definition["function"]["description"]

        assert "创建前应询问用户希望将技能归入哪个分类" in description
        assert "用户不指定时使用 uncategorized" in description
        assert "frontmatter 中填写 category 字段" in description
