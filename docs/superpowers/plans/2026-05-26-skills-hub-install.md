# Skills Hub 安装工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `skill_hub_install` 工具，支持从 GitHub 仓库或直接 URL 安装外部技能到 `workspace/skills/`。

**Architecture:** 新增 `tools/skill_hub.py`，实现 `handle_skill_hub_install` 函数并注册到全局 registry。GitHub 源通过 Contents API 获取目录文件列表后逐文件下载，URL 源通过 HTTP GET 获取 SKILL.md。冲突检测依赖 `resolve_skill_dir`（已有）和 `lock.json`。

**Tech Stack:** Python 3.11+, `urllib.request`, `json`, `hashlib`, `pathlib`

**Design Spec:** `docs/superpowers/specs/phase3-skills-hub-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `config/settings.py` | 新增 `SkillsHubConfig` dataclass，`AppConfig` 新增 `skills_hub` 字段 |
| `config.yaml.example` | 新增 `skills_hub` 配置段示例 |
| `tools/skill_hub.py` | `skill_hub_install` 工具全部实现（GitHub + URL 源、lock.json 管理） |
| `tools/__init__.py` | 新增 `import tools.skill_hub` |
| `agent/prompt.py` | `SKILLS_GUIDANCE` 补充 Hub 安装指引 |
| `tests/test_skill_hub.py` | 全部测试 |

---

### Task 1: Config infrastructure — SkillsHubConfig

**Files:**
- Modify: `config/settings.py`
- Modify: `config.yaml.example`

- [ ] **Step 1: Add SkillsHubConfig dataclass and AppConfig field**

In `config/settings.py`, add after `ApprovalConfig` (line 64):

```python
@dataclass
class SkillsHubConfig:
    """Skills Hub 配置"""
    github_token: str = ""
```

In `AppConfig` (line 67), add after `approval`:

```python
    skills_hub: SkillsHubConfig = field(default_factory=SkillsHubConfig)
```

In `load_config` (line 102), add after `approval_dict` extraction:

```python
    skills_hub_dict = config_dict.pop("skills_hub", {})
```

And in the `AppConfig(...)` constructor, add after `approval=ApprovalConfig(**approval_dict) if approval_dict else ApprovalConfig(),`:

```python
        skills_hub=SkillsHubConfig(**skills_hub_dict) if skills_hub_dict else SkillsHubConfig(),
```

- [ ] **Step 2: Verify config loads correctly**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && source .venv/bin/activate && python3 -c "
from config.settings import load_config
c = load_config()
assert c.skills_hub.github_token == ''
print('OK:', c.skills_hub)
"
```

Expected: `OK: SkillsHubConfig(github_token='')`

- [ ] **Step 3: Add example config section**

In `config.yaml.example`, append before the path config section:

```yaml
# ----------------------------------------------------------
# Skills Hub 配置（从外部源安装技能）
# ----------------------------------------------------------
skills_hub:
  github_token: ""            # GitHub personal access token（可选，不填则匿名访问，60 req/hr 限制）
```

- [ ] **Step 4: Commit**

```bash
git add config/settings.py config.yaml.example
git commit -m "feat: add SkillsHubConfig for external skill installation
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Core tool tests (TDD — write failing tests first)

**Files:**
- Create: `tests/test_skill_hub.py`

- [ ] **Step 1: Write the test file with all test cases**

```python
"""skill_hub_install 工具测试"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

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
                    {"name": "SKILL.md", "type": "file", "download_url": "https://api.github.com/repos/owner/repo/skill/SKILL.md"},
                ]
                with patch("tools.skill_hub._github_download") as mock_dl:
                    mock_dl.return_value = "---\nname: my-skill\ndescription: \"Test\"\ncategory: dev\n---\nBody."

                    result = json.loads(handle_skill_hub_install({
                        "source": "github",
                        "identifier": "owner/repo/skill",
                    }))

            assert "error" in result
            assert "my-skill" in result["error"]
        finally:
            tmp.cleanup()

    def test_github_api_error(self):
        tmp, root = _setup_skills_dir()
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
        tmp, root = _setup_skills_dir()
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
        tmp, root = _setup_skills_dir()
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
        tmp, root = _setup_skills_dir()
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
        tmp, root = _setup_skills_dir()
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && source .venv/bin/activate && python3 -m pytest tests/test_skill_hub.py -v 2>&1 | tail -20
```

Expected: All tests FAIL (module/tool not yet implemented)

---

### Task 3: Implement `tools/skill_hub.py`

**Files:**
- Create: `tools/skill_hub.py`

- [ ] **Step 1: Implement the full module**

```python
"""Skills Hub 工具：从外部源安装技能"""

import hashlib
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skills.skill_utils import parse_frontmatter, resolve_skill_dir
from tools.registry import registry

logger = logging.getLogger(__name__)

_skills_dir: Path | None = None


def set_skills_dir(path: Path | None) -> None:
    global _skills_dir
    _skills_dir = path


def _check_dir() -> str | None:
    if _skills_dir is None:
        return json.dumps({"error": "技能目录未配置"}, ensure_ascii=False)
    return None


def _load_lock() -> dict:
    lock_path = _skills_dir / ".hub" / "lock.json"
    if not lock_path.is_file():
        return {"version": 1, "installed": {}}
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "installed": {}}


def _save_lock(lock: dict) -> None:
    hub_dir = _skills_dir / ".hub"
    hub_dir.mkdir(parents=True, exist_ok=True)
    (hub_dir / "lock.json").write_text(json.dumps(lock, indent=2, ensure_ascii=False), encoding="utf-8")


def _content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _github_api(path: str, token: str = "") -> list[dict]:
    """调用 GitHub Contents API 获取目录文件列表"""
    url = f"https://api.github.com/repos/{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "F-Agent")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list):
        raise Exception(f"Unexpected GitHub API response: not a directory listing")
    return data


def _github_download(url: str, token: str = "") -> str:
    """下载单个文件内容"""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3.raw")
    req.add_header("User-Agent", "F-Agent")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read().decode("utf-8")


def _url_fetch(url: str) -> str:
    """通过 HTTP GET 获取 URL 内容"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "F-Agent")
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read().decode("utf-8")


def _collect_github_files(owner: str, repo: str, skill_path: str, token: str) -> list[tuple[str, str]]:
    """递归收集 GitHub 目录下所有文件的 (relative_path, content)"""
    files: list[tuple[str, str]] = []
    api_path = f"{owner}/{repo}/contents/{skill_path}"

    entries = _github_api(api_path, token)
    for entry in entries:
        name = entry["name"]
        if entry["type"] == "file":
            content = _github_download(entry["download_url"], token)
            files.append((name, content))
        elif entry["type"] == "dir":
            # Recursively collect subdirectory files
            sub_path = f"{skill_path}/{name}"
            sub_files = _collect_github_files(owner, repo, sub_path, token)
            for sub_name, sub_content in sub_files:
                files.append((f"{name}/{sub_name}", sub_content))

    return files


def handle_skill_hub_install(args: dict[str, Any]) -> str:
    err = _check_dir()
    if err:
        return err

    source = args.get("source", "")
    identifier = args.get("identifier", "")
    override_name = args.get("name")
    override_category = args.get("category")

    if source not in ("github", "url"):
        return json.dumps({
            "error": f"不支持来源: {source}，可用: github, url"
        }, ensure_ascii=False)

    if not identifier:
        return json.dumps({"error": "identifier is required"}, ensure_ascii=False)

    # --- Fetch files ---
    files: list[tuple[str, str]] = []

    try:
        if source == "github":
            from config.settings import load_config
            config = load_config()
            token = config.skills_hub.github_token

            # Parse identifier: owner/repo/path/to/skill
            parts = identifier.split("/", 2)
            if len(parts) < 3:
                return json.dumps({
                    "error": f"无效的 GitHub identifier 格式: {identifier}，应为 owner/repo/path/to/skill"
                }, ensure_ascii=False)
            owner, repo, skill_path = parts[0], parts[1], parts[2]
            files = _collect_github_files(owner, repo, skill_path, token)

        elif source == "url":
            content = _url_fetch(identifier)
            files = [("SKILL.md", content)]

    except Exception as e:
        error_msg = str(e)
        if source == "github":
            return json.dumps({
                "error": f"GitHub API 请求失败: {error_msg}"
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "error": f"URL 请求失败: {error_msg}"
            }, ensure_ascii=False)

    if not files:
        return json.dumps({"error": "未找到任何文件"}, ensure_ascii=False)

    # --- Parse frontmatter from SKILL.md ---
    skill_md_content = None
    other_files: list[tuple[str, str]] = []

    for rel_path, content in files:
        if rel_path == "SKILL.md":
            skill_md_content = content
        else:
            other_files.append((rel_path, content))

    if skill_md_content is None:
        return json.dumps({"error": "未找到 SKILL.md 文件"}, ensure_ascii=False)

    meta, _body = parse_frontmatter(skill_md_content)
    skill_name = override_name or meta.get("name")
    if not skill_name:
        return json.dumps({"error": "SKILL.md 缺少 name 字段"}, ensure_ascii=False)
    skill_name = str(skill_name)

    category = override_category or str(meta.get("category", "uncategorized"))

    # --- Check conflicts ---
    # 1. Check workspace/skills/ directory
    existing = resolve_skill_dir(str(_skills_dir), str(skill_name))
    if existing:
        return json.dumps({
            "error": f"技能已存在: {skill_name}",
            "hint": "如需重新安装，请先手动删除该技能"
        }, ensure_ascii=False)

    # 2. Check lock.json
    lock = _load_lock()
    if str(skill_name) in lock.get("installed", {}):
        return json.dumps({
            "error": f"技能已安装(lock.json): {skill_name}",
            "hint": "如需重新安装，请先手动删除该技能"
        }, ensure_ascii=False)

    # --- Write files ---
    skill_dir = _skills_dir / category / str(skill_name)
    skill_dir.mkdir(parents=True, exist_ok=False)

    (skill_dir / "SKILL.md").write_text(skill_md_content, encoding="utf-8")

    written_files = ["SKILL.md"]
    for rel_path, content in other_files:
        file_path = skill_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        written_files.append(rel_path)

    # --- Record lock.json ---
    all_content = skill_md_content + "".join(c for _, c in other_files)
    lock["installed"][str(skill_name)] = {
        "source": source,
        "identifier": identifier,
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "content_hash": _content_hash(all_content),
    }
    _save_lock(lock)

    logger.info("Skill installed from hub: %s (source=%s)", skill_name, source)

    return json.dumps({
        "status": "installed",
        "name": str(skill_name),
        "category": category,
        "path": str(skill_dir),
        "files": sorted(written_files),
        "note": "重启会话后生效",
    }, ensure_ascii=False)


# Register tool on global registry
registry.register(
    name="skill_hub_install",
    schema={
        "type": "function",
        "function": {
            "name": "skill_hub_install",
            "description": "从 GitHub 或 URL 安装外部技能，安装后重启会话生效",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "技能来源：github 或 url",
                        "enum": ["github", "url"],
                    },
                    "identifier": {
                        "type": "string",
                        "description": "技能标识。github 格式为 owner/repo/path/to/skill，url 格式为 https://.../SKILL.md",
                    },
                    "name": {
                        "type": "string",
                        "description": "可选：覆盖 frontmatter 中的技能名称",
                    },
                    "category": {
                        "type": "string",
                        "description": "可选：指定安装分类，不填则使用 frontmatter 中的 category 或默认值",
                    },
                },
                "required": ["source", "identifier"],
            },
        },
    },
    handler=handle_skill_hub_install,
    parallel_safe=False,
)
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && source .venv/bin/activate && python3 -m pytest tests/test_skill_hub.py -v
```

Expected: All 14 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tools/skill_hub.py tests/test_skill_hub.py
git commit -m "feat: add skill_hub_install tool with GitHub and URL source support
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Register tool in __init__.py

**Files:**
- Modify: `tools/__init__.py`

- [ ] **Step 1: Add import line**

In `tools/__init__.py`, add after line 9 (`import tools.skill`):

```python
import tools.skill_hub
```

- [ ] **Step 2: Verify import works and tool is registered**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && source .venv/bin/activate && python3 -c "
import tools  # triggers all imports
from tools.registry import registry
names = [d['function']['name'] for d in registry.get_definitions()]
assert 'skill_hub_install' in names, f'skill_hub_install not in {names}'
print('OK: skill_hub_install registered')
"
```

Expected: `OK: skill_hub_install registered`

- [ ] **Step 3: Commit**

```bash
git add tools/__init__.py
git commit -m "feat: register skill_hub tool in tools __init__
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Update system prompt with Hub guidance

**Files:**
- Modify: `agent/prompt.py`

- [ ] **Step 1: Add Hub install guidance to SKILLS_GUIDANCE**

In `agent/prompt.py`, append to the `SKILLS_GUIDANCE` string (after line 62, before the closing `"""`):

```python

### 安装外部技能
用户要求安装外部技能时，使用 skill_hub_install 工具：
- GitHub 源：skill_hub_install(source="github", identifier="owner/repo/path/to/skill")
- URL 源：skill_hub_install(source="url", identifier="https://.../SKILL.md")
安装前告知用户技能名称和来源，安装后提示重启会话生效。
```

The `SKILLS_GUIDANCE` string should end with:

```python
### 安装外部技能
用户要求安装外部技能时，使用 skill_hub_install 工具：
- GitHub 源：skill_hub_install(source="github", identifier="owner/repo/path/to/skill")
- URL 源：skill_hub_install(source="url", identifier="https://.../SKILL.md")
安装前告知用户技能名称和来源，安装后提示重启会话生效。
"""
```

- [ ] **Step 2: Verify prompt builds correctly**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && source .venv/bin/activate && python3 -c "
from agent.prompt import SKILLS_GUIDANCE
assert 'skill_hub_install' in SKILLS_GUIDANCE
assert 'GitHub' in SKILLS_GUIDANCE
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && source .venv/bin/activate && python3 -m pytest tests/ -v
```

Expected: All tests pass (no regressions)

- [ ] **Step 4: Commit**

```bash
git add agent/prompt.py
git commit -m "feat: add skills hub install guidance to system prompt
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- Config infrastructure → Task 1
- GitHub source (Contents API, recursive download, token auth) → Task 3
- URL source (HTTP GET, single file) → Task 3
- Frontmatter parsing (reuse `parse_frontmatter`) → Task 3
- Conflict detection (resolve_skill_dir + lock.json) → Task 3
- lock.json management → Task 3
- Error handling (all 5 scenarios) → Task 2/3
- System prompt guidance → Task 5
- Tool registration → Task 3/4
- Parameter schema (source, identifier, name, category) → Task 3

**2. Placeholder scan:** No TBD/TODO/fill-in-later patterns found.

**3. Type consistency:**
- `handle_skill_hub_install(args: dict[str, Any]) -> str` — consistent across tests and implementation
- `set_skills_dir(path: Path | None) -> None` — matches existing pattern in `tools/skill.py`
- `_github_api`, `_github_download`, `_url_fetch` — all return types consistent with callers