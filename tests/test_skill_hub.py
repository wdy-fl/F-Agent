"""skill_hub_install 工具测试"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.registry import registry
from tools.skill_hub import handle_skill_hub_install, set_skills_dir


def _setup_skills_dir():
    """创建临时技能目录并注入"""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    set_skills_dir(root)
    return tmp, root


class TestSkillHubInstallGitHub:
    """GitHub 源安装测试"""

    def test_install_from_github_success(self):
        tmp, root = _setup_skills_dir()
        try:
            # Mock GitHub API returns directory listing then file contents
            with patch("tools.skill_hub._github_api") as mock_api:
                # First call: list directory
                mock_api.side_effect = [
                    # list response
                    [
                        {"name": "SKILL.md", "type": "file", "download_url": "https://api.github.com/repos/owner/repo/contents/skill/SKILL.md"},
                        {"name": "references", "type": "dir", "path": "skill/references"},
                    ],
                    # references/ listing
                    [
                        {"name": "guide.md", "type": "file", "download_url": "https://api.github.com/repos/owner/repo/contents/skill/references/guide.md"},
                    ],
                ]
                # Mock _github_download for individual file content
                with patch("tools.skill_hub._github_download") as mock_dl:
                    mock_dl.side_effect = [
                        "---\nname: my-skill\ndescription: \"A test skill\"\ncategory: dev\n---\n# my-skill\nInstructions.",
                        "# Reference Guide\nSome content.",
                    ]

                    result = json.loads(handle_skill_hub_install({
                        "source": "github",
                        "identifier": "owner/repo/skill",
                    }))

            assert result["status"] == "installed"
            assert result["name"] == "my-skill"
            assert result["category"] == "dev"
            assert "my-skill" in result["path"]

            # Verify files written
            skill_dir = root / "dev" / "my-skill"
            assert skill_dir.is_dir()
            assert (skill_dir / "SKILL.md").is_file()
            assert (skill_dir / "references" / "guide.md").is_file()

            # Verify lock.json
            lock_path = root / ".hub" / "lock.json"
            assert lock_path.is_file()
            lock = json.loads(lock_path.read_text())
            assert "my-skill" in lock["installed"]
            assert lock["installed"]["my-skill"]["source"] == "github"
            assert lock["installed"]["my-skill"]["identifier"] == "owner/repo/skill"
        finally:
            tmp.cleanup()

    def test_install_with_custom_name_and_category(self):
        tmp, root = _setup_skills_dir()
        try:
            with patch("tools.skill_hub._github_api") as mock_api:
                mock_api.return_value = [
                    {"name": "SKILL.md", "type": "file", "download_url": "https://api.github.com/repos/owner/repo/contents/skill/SKILL.md"},
                ]
                with patch("tools.skill_hub._github_download") as mock_dl:
                    mock_dl.return_value = "---\nname: original-name\ndescription: \"Original desc\"\ncategory: dev\n---\nBody."

                    result = json.loads(handle_skill_hub_install({
                        "source": "github",
                        "identifier": "owner/repo/skill",
                        "name": "custom-name",
                        "category": "tools",
                    }))

            assert result["status"] == "installed"
            assert result["name"] == "custom-name"
            assert result["category"] == "tools"
            assert (root / "tools" / "custom-name" / "SKILL.md").is_file()
        finally:
            tmp.cleanup()

    def test_install_duplicate_skill(self):
        tmp, root = _setup_skills_dir()
        try:
            # Pre-create a skill with the same name
            skill_dir = root / "dev" / "my-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ncategory: dev\n---\nBody.")

            with patch("tools.skill_hub._github_api") as mock_api:
                mock_api.return_value = [
                    {"name": "SKILL.md", "type": "file", "download_url": "https://api.github.com/repos/owner/repo/contents/skill/SKILL.md"},
                ]
                with patch("tools.skill_hub._github_download") as mock_dl:
                    mock_dl.return_value = "---\nname: my-skill\ndescription: \"Test\"\ncategory: dev\n---\nBody."

                    result = json.loads(handle_skill_hub_install({
                        "source": "github",
                        "identifier": "owner/repo/skill",
                    }))

            assert "error" in result
            assert "my-skill" in result["error"]
            assert "hint" in result
        finally:
            tmp.cleanup()

    def test_install_already_in_lock(self):
        tmp, root = _setup_skills_dir()
        try:
            # Pre-create lock.json with the skill already installed
            hub_dir = root / ".hub"
            hub_dir.mkdir(parents=True)
            (hub_dir / "lock.json").write_text(json.dumps({
                "version": 1,
                "installed": {
                    "my-skill": {
                        "source": "github",
                        "identifier": "owner/repo/skill",
                        "installed_at": "2026-05-25T12:00:00Z",
                        "content_hash": "sha256:abc123",
                    }
                }
            }))

            with patch("tools.skill_hub._github_api") as mock_api:
                mock_api.return_value = [
                    {"name": "SKILL.md", "type": "file", "download_url": "https://api.github.com/repos/owner/repo/contents/skill/SKILL.md"},
                ]
                with patch("tools.skill_hub._github_download") as mock_dl:
                    mock_dl.return_value = "---\nname: my-skill\ndescription: \"Test\"\ncategory: dev\n---\nBody."

                    result = json.loads(handle_skill_hub_install({
                        "source": "github",
                        "identifier": "owner/repo/skill",
                    }))

            mock_api.assert_not_called()

            assert "error" in result
            assert "my-skill" in result["error"]
        finally:
            tmp.cleanup()

    def test_github_api_error(self):
        tmp, _ = _setup_skills_dir()
        try:
            with patch("tools.skill_hub._github_api") as mock_api:
                mock_api.side_effect = Exception("403 Forbidden")

                result = json.loads(handle_skill_hub_install({
                    "source": "github",
                    "identifier": "owner/repo/skill",
                }))

            assert "error" in result
            assert "GitHub" in result["error"]
        finally:
            tmp.cleanup()

    def test_invalid_identifier_format(self):
        tmp, _ = _setup_skills_dir()
        try:
            result = json.loads(handle_skill_hub_install({
                "source": "github",
                "identifier": "only-one-part",
            }))
            assert "error" in result
            assert "identifier" in result["error"].lower()
        finally:
            tmp.cleanup()

    def test_missing_name_in_frontmatter(self):
        tmp, _ = _setup_skills_dir()
        try:
            with patch("tools.skill_hub._github_api") as mock_api:
                mock_api.return_value = [
                    {"name": "SKILL.md", "type": "file", "download_url": "https://api.github.com/repos/owner/repo/contents/skill/SKILL.md"},
                ]
                with patch("tools.skill_hub._github_download") as mock_dl:
                    mock_dl.return_value = "---\ndescription: \"No name field\"\n---\nBody without name."

                    result = json.loads(handle_skill_hub_install({
                        "source": "github",
                        "identifier": "owner/repo/skill",
                    }))

            assert "error" in result
            assert "name" in result["error"].lower()
        finally:
            tmp.cleanup()


class TestSkillHubInstallURL:
    """URL 源安装测试"""

    def test_install_from_url_success(self):
        tmp, root = _setup_skills_dir()
        try:
            with patch("tools.skill_hub._url_fetch") as mock_fetch:
                mock_fetch.return_value = "---\nname: url-skill\ndescription: \"Installed from URL\"\ncategory: tools\n---\n# url-skill\nURL instructions."

                result = json.loads(handle_skill_hub_install({
                    "source": "url",
                    "identifier": "https://example.com/skills/my-skill/SKILL.md",
                }))

            assert result["status"] == "installed"
            assert result["name"] == "url-skill"
            assert result["category"] == "tools"

            skill_dir = root / "tools" / "url-skill"
            assert skill_dir.is_dir()
            assert (skill_dir / "SKILL.md").is_file()

            # Verify lock.json
            lock_path = root / ".hub" / "lock.json"
            assert lock_path.is_file()
            lock = json.loads(lock_path.read_text())
            assert "url-skill" in lock["installed"]
            assert lock["installed"]["url-skill"]["source"] == "url"
        finally:
            tmp.cleanup()

    def test_url_request_error(self):
        tmp, _ = _setup_skills_dir()
        try:
            with patch("tools.skill_hub._url_fetch") as mock_fetch:
                mock_fetch.side_effect = Exception("404 Not Found")

                result = json.loads(handle_skill_hub_install({
                    "source": "url",
                    "identifier": "https://example.com/not-found/SKILL.md",
                }))

            assert "error" in result
            assert "URL" in result["error"]
        finally:
            tmp.cleanup()

    def test_url_duplicate_skill(self):
        tmp, root = _setup_skills_dir()
        try:
            skill_dir = root / "tools" / "url-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: url-skill\ncategory: tools\n---\nBody.")

            with patch("tools.skill_hub._url_fetch") as mock_fetch:
                mock_fetch.return_value = "---\nname: url-skill\ndescription: \"Test\"\ncategory: tools\n---\nBody."

                result = json.loads(handle_skill_hub_install({
                    "source": "url",
                    "identifier": "https://example.com/skills/SKILL.md",
                }))

            assert "error" in result
            assert "url-skill" in result["error"]
        finally:
            tmp.cleanup()

    def test_url_missing_name(self):
        tmp, _ = _setup_skills_dir()
        try:
            with patch("tools.skill_hub._url_fetch") as mock_fetch:
                mock_fetch.return_value = "---\ndescription: \"No name\"\n---\nBody."

                result = json.loads(handle_skill_hub_install({
                    "source": "url",
                    "identifier": "https://example.com/SKILL.md",
                }))

            assert "error" in result
            assert "name" in result["error"].lower()
        finally:
            tmp.cleanup()


class TestSkillHubEdgeCases:
    """边界情况测试"""

    def test_unknown_source(self):
        result = json.loads(handle_skill_hub_install({
            "source": "unknown",
            "identifier": "something",
        }))
        assert "error" in result
        assert "source" in result["error"].lower()

    def test_missing_required_params(self):
        result = json.loads(handle_skill_hub_install({}))
        assert "error" in result

    def test_skills_dir_not_set(self):
        set_skills_dir(None)
        result = json.loads(handle_skill_hub_install({
            "source": "github",
            "identifier": "owner/repo/skill",
        }))
        assert "error" in result


class TestSkillHubRegistered:
    """工具注册测试"""

    def test_skill_hub_install_registered(self):
        import tools.skill_hub  # noqa: F401 — trigger registration
        names = [d["function"]["name"] for d in registry.get_definitions()]
        assert "skill_hub_install" in names

    def test_skill_hub_install_description_includes_confirmation_contract(self):
        import tools.skill_hub  # noqa: F401 — trigger registration

        definition = next(
            d for d in registry.get_definitions()
            if d["function"]["name"] == "skill_hub_install"
        )
        description = definition["function"]["description"]

        assert "先向用户确认技能名称、来源和分类" in description
        assert "GitHub 源" in description
        assert "URL 源" in description
        assert "用户不指定分类时" in description
