# Phase 3 技能系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 F-Agent 技能系统的最小可用版本——Agent 从经验中创建技能并复用，使用渐进式披露机制注入系统提示词。

**Architecture:** 新增 `skills/skill_utils.py`（frontmatter 解析/名称校验）、`skills/loader.py`（扫描+索引+提示词格式化）、`tools/skill.py`（三个工具：skills_list/skill_view/skill_manage），修改 `agent/prompt.py`（注入 SKILLS_GUIDANCE 和技能索引）和 `tools/__init__.py`（导入新工具模块）。技能存储在 `workspace/skills/`。

**Tech Stack:** Python 3.11+, PyYAML (已有依赖), pytest

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `skills/skill_utils.py` | 新增 | frontmatter 解析（YAML→dict+body）、名称校验、路径解析 |
| `skills/loader.py` | 新增 | 扫描 workspace/skills/、构建索引、格式化 `<available_skills>` 文本 |
| `tools/skill.py` | 新增 | skills_list/skill_view/skill_manage 三个工具注册+handler |
| `agent/prompt.py` | 修改 | 注入 SKILLS_GUIDANCE + skills 索引到系统提示词 |
| `tools/__init__.py` | 修改 | 添加 `import tools.skill` |
| `skills/__init__.py` | 修改 | 保持空文件（模块标记） |
| `tests/test_skill_utils.py` | 新增 | skill_utils 单元测试 |
| `tests/test_skill_loader.py` | 新增 | loader 扫描+索引测试 |
| `tests/test_skill_tools.py` | 新增 | 工具注册+handler 各 action 测试 |

`config/settings.py` 已有 `DEFAULT_SKILLS_DIR = DEFAULT_CONFIG_DIR / "skills"`，无需修改。

---

### Task 1: skill_utils.py — frontmatter 解析与名称校验

**Files:**
- Create: `skills/skill_utils.py`
- Create: `tests/test_skill_utils.py`

- [ ] **Step 1: 编写测试**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```
Run: source .venv/bin/activate && python3 -m pytest tests/test_skill_utils.py -v
Expected: 全部 FAIL（模块不存在）
```

- [ ] **Step 3: 实现 skill_utils.py**

```python
"""技能系统共享工具：frontmatter 解析、名称校验、路径解析"""

import re
from pathlib import Path

import yaml


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (meta_dict, body_text)

    若无 frontmatter 或解析失败，返回 ({}, content)。
    """
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}, content

    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, content

    if not isinstance(meta, dict):
        return {}, content

    body = content[m.end():]
    return meta, body


def validate_skill_name(name: str) -> str | None:
    """校验技能名称，合法返回 None，非法返回错误描述文字"""
    if not name:
        return "技能名称不能为空"
    if not _NAME_RE.match(name):
        return f"技能名称仅允许字母/数字/连字符/下划线，最长 64 字符: {name}"
    return None


def resolve_skill_dir(root: str, name: str) -> str | None:
    """在 root 目录下按名称查找技能目录，返回第一个匹配的绝对路径

    遍历 root/{category}/{name}/SKILL.md，找到第一个即返回。
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return None

    for category_dir in sorted(root_path.iterdir()):
        if not category_dir.is_dir():
            continue
        skill_dir = category_dir / name
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            return str(skill_dir)

    return None


_SKILL_MD_FRONTMATTER_TEMPLATE = """---
name: {name}
description: {description}
category: {category}
created_at: {created_at}
updated_at: {updated_at}
---
"""
```

- [ ] **Step 4: 运行测试确认通过**

```
Run: source .venv/bin/activate && python3 -m pytest tests/test_skill_utils.py -v
Expected: 全部 PASS
```

- [ ] **Step 5: 提交**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && git add skills/skill_utils.py tests/test_skill_utils.py && git commit -m "feat: add skill_utils.py — frontmatter 解析、名称校验、路径解析"
```

---

### Task 2: loader.py — 技能扫描与索引构建

**Files:**
- Create: `skills/loader.py`
- Create: `tests/test_skill_loader.py`

- [ ] **Step 1: 编写测试**

```python
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
            assert skill.name == "test-skill"
            assert skill.category == "dev"
            assert "Body text." in skill.body

    def test_load_skill_file_not_found(self):
        from skills.loader import load_skill
        skill = load_skill("/nonexistent/SKILL.md")
        assert skill is None


class TestGetSkillsPrompt:
    def test_format_empty_index(self):
        result = get_skills_prompt([])
        assert "暂无可用技能" in result

    def test_format_grouped_by_category(self):
        entries = [
            SkillIndex(name="py-test", description="Python testing", category="dev", path="/tmp/dev/py-test/SKILL.md"),
            SkillIndex(name="data-sql", description="SQL queries", category="data", path="/tmp/data/data-sql/SKILL.md"),
            SkillIndex(name="git-flow", description="Git workflow", category="dev", path="/tmp/dev/git-flow/SKILL.md"),
        ]
        result = get_skills_prompt(entries)
        assert "## dev" in result
        assert "## data" in result
        assert "py-test" in result
        assert "data-sql" in result
        assert "git-flow" in result
```

- [ ] **Step 2: 运行测试确认失败**

```
Run: source .venv/bin/activate && python3 -m pytest tests/test_skill_loader.py -v
Expected: 全部 FAIL
```

- [ ] **Step 3: 实现 loader.py**

```python
"""技能加载器：扫描 workspace/skills/、构建索引、格式化提示词"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from skills.skill_utils import parse_frontmatter


@dataclass
class SkillIndex:
    """技能索引条目"""
    name: str
    description: str
    category: str
    path: str


def scan_skills(root: str) -> list[str]:
    """扫描技能目录，返回所有 SKILL.md 文件路径列表"""
    root_path = Path(root)
    if not root_path.is_dir():
        return []

    skill_files: list[str] = []
    for category_dir in sorted(root_path.iterdir()):
        if not category_dir.is_dir():
            continue
        for skill_dir in sorted(category_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.is_file():
                skill_files.append(str(skill_md))

    return skill_files


def build_index(root: str) -> list[SkillIndex]:
    """扫描并构建技能索引"""
    skill_files = scan_skills(root)
    index: list[SkillIndex] = []

    for file_path in skill_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            continue

        meta, _ = parse_frontmatter(content)
        if not meta.get("name"):
            continue

        index.append(SkillIndex(
            name=meta["name"],
            description=meta.get("description", ""),
            category=meta.get("category", "uncategorized"),
            path=file_path,
        ))

    return index


def load_skill(path: str) -> SkillIndex | None:
    """读取单个 SKILL.md，返回 SkillIndex（含 body）"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    meta, body = parse_frontmatter(content)
    if not meta.get("name"):
        return None

    return SkillIndex(
        name=meta["name"],
        description=meta.get("description", ""),
        category=meta.get("category", "uncategorized"),
        path=path,
    )


def get_skills_prompt(index: list[SkillIndex]) -> str:
    """将技能索引格式化为 <available_skills> 文本"""
    if not index:
        return "<available_skills>\n(暂无可用技能)\n</available_skills>"

    by_category: dict[str, list[SkillIndex]] = defaultdict(list)
    for entry in index:
        by_category[entry.category].append(entry)

    lines = ["<available_skills>"]
    for category in sorted(by_category):
        lines.append(f"## {category}")
        for entry in by_category[category]:
            lines.append(f"- {entry.name}: {entry.description}")
    lines.append("</available_skills>")

    return "\n".join(lines)
```

注意：`load_skill` 返回的 `SkillIndex` 需要支持 `.body` 属性。更新 `SkillIndex` dataclass：

在实现时修改 `SkillIndex` 为：

```python
@dataclass
class SkillIndex:
    name: str
    description: str
    category: str
    path: str
    body: str = ""  # SKILL.md 正文（不含 frontmatter）
```

同步更新 `load_skill` 中将 body 赋值给 SkillIndex，`build_index` 不需要 body（节省内存）。

- [ ] **Step 4: 运行测试确认通过**

```
Run: source .venv/bin/activate && python3 -m pytest tests/test_skill_loader.py -v
Expected: 全部 PASS
```

- [ ] **Step 5: 提交**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && git add skills/loader.py tests/test_skill_loader.py && git commit -m "feat: add loader.py — 技能扫描、索引构建、提示词格式化"
```

---

### Task 3: tools/skill.py — 技能工具注册

**Files:**
- Create: `tools/skill.py`
- Create: `tests/test_skill_tools.py`

- [ ] **Step 1: 编写测试**

```python
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
created_at: 2026-05-24
updated_at: 2026-05-24
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
                "content": "---\nname: exist-skill\n---\nBody.",
            }))
            assert "error" in result

    def test_create_invalid_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_skills_dir(root)

            result = json.loads(handle_skill_manage({
                "action": "create",
                "name": "bad name!",
                "content": "---\nname: bad name!\n---\nBody.",
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
            "content": "---\nname: test\n---\nBody.",
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
                "content": "---\nname: nonexistent\n---\nBody.",
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
            # 写入默认位置
            assert (root / "dev" / "python-testing" / result["path"]).is_file()
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
```

- [ ] **Step 2: 运行测试确认失败**

```
Run: source .venv/bin/activate && python3 -m pytest tests/test_skill_tools.py -v
Expected: 全部 FAIL（模块不存在）
```

- [ ] **Step 3: 实现 tools/skill.py**

```python
"""技能管理工具：供 LLM 调用 skills_list/skill_view/skill_manage"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from skills.loader import build_index, load_skill
from skills.skill_utils import parse_frontmatter, resolve_skill_dir, validate_skill_name
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
    """加载技能的完整 SKILL.md 正文"""
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

        meta, body = parse_frontmatter(content)
        category = meta.get("category", "uncategorized")
        now = datetime.now().strftime("%Y-%m-%d")
        if "created_at" not in meta:
            content = f"created_at: {now}\n" + content
        if "updated_at" not in meta:
            content = f"updated_at: {now}\n" + content

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
        (Path(skill_dir) / "SKILL.md").write_text(content, encoding="utf-8")
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


# 注册工具
registry.register(
    name="skills_list",
    schema={
        "type": "function",
        "function": {
            "name": "skills_list",
            "description": "列出所有可用技能的名称和描述。回复前先检查是否有相关技能可用。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
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
                    "name": {
                        "type": "string",
                        "description": "要加载的技能名称",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "可选：技能目录下的关联文件相对路径，如 references/note.md",
                    },
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
                    "name": {
                        "type": "string",
                        "description": "目标技能名称（必需）",
                    },
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
```

- [ ] **Step 4: 运行测试确认通过**

```
Run: source .venv/bin/activate && python3 -m pytest tests/test_skill_tools.py -v
Expected: 全部 PASS
```

- [ ] **Step 5: 提交**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && git add tools/skill.py tests/test_skill_tools.py && git commit -m "feat: add tools/skill.py — skills_list/skill_view/skill_manage 三个工具"
```

---

### Task 4: agent/prompt.py — 注入技能索引和 SKILLS_GUIDANCE

**Files:**
- Modify: `agent/prompt.py`

- [ ] **Step 1: 修改 prompt.py，新增 SKILLS_GUIDANCE 和 build_skills_section 函数**

在 `agent/prompt.py` 中，在 `MEMORY_GUIDANCE` 之后新增：

```python
SKILLS_GUIDANCE = """\
## 技能系统
你有可用的技能（Skills）——它们是程序性记忆，存储了经过验证的完成特定任务的方法和流程。

### 使用方式
- 回复前先检查 <available_skills> 索引，如果有与当前任务相关的技能，调用 skill_view(name) 加载完整指令并遵循
- 使用技能时发现内容过时、不完整或错误，用 skill_manage(action='edit') 修正

### 创建技能
在以下情况，用 skill_manage 保存方法供将来复用：
- 完成复杂任务（5+ 次工具调用）后
- 克服棘手错误并找到解决方案后
- 用户纠正过的做法最终生效后
- 发现非平凡的工作流程后
- 用户明确要求"记住这个做法/步骤"时

创建技能时使用清晰的名称和描述，内容应具体、可执行，像"配方"而非"常识"。创建/删除前必须征求用户确认。技能变更后需重启会话才能生效。
"""


def build_skills_section(skills_dir: str) -> str:
    """构建技能索引提示词段落"""
    from skills.loader import build_index, get_skills_prompt
    index = build_index(skills_dir)
    return get_skills_prompt(index)
```

修改 `build_system_prompt` 函数签名和实现：

```python
def build_system_prompt(
    include_tools: bool = False,
    include_memory_guidance: bool = True,
    include_skills: bool = False,
    skills_dir: str = "",
) -> str:
    """构建系统提示词

    Args:
        include_tools: 是否包含工具使用指引
        include_memory_guidance: 是否包含记忆系统指引
        include_skills: 是否包含技能系统指引和索引
        skills_dir: 技能目录路径
    """
    parts = [AGENT_IDENTITY]

    if include_tools:
        tool_index = _build_tool_index()
        parts.append(TOOL_USE_GUIDANCE.format(tool_index=tool_index))

    if include_skills and skills_dir:
        parts.append(SKILLS_GUIDANCE)
        parts.append(build_skills_section(skills_dir))

    if include_memory_guidance:
        parts.append(MEMORY_GUIDANCE)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts.append(f"\n当前时间：{now}")

    return "\n".join(parts)
```

- [ ] **Step 2: 修改 agent/loop.py 中 build_system_prompt 调用**

在 `agent/loop.py` 第 58 行，将：

```python
self.system_prompt = build_system_prompt(include_tools=True)
```

改为：

```python
self.system_prompt = build_system_prompt(
    include_tools=True,
    include_skills=True,
    skills_dir=config.skills_dir,
)
```

在 `loop.py` 的导入区域添加：

```python
from pathlib import Path
from tools.skill import set_skills_dir
```

在 `__init__` 中 `set_managers(...)` 之后添加：

```python
set_skills_dir(Path(config.skills_dir))
```

- [ ] **Step 3: 修改 tools/__init__.py，导入 skill 模块**

在 `tools/__init__.py` 末尾添加：

```python
import tools.skill
```

- [ ] **Step 4: 运行现有测试确保无回归**

```
Run: source .venv/bin/activate && python3 -m pytest tests/test_tools.py tests/test_memory_tool.py tests/test_agent_loop.py -v
Expected: 全部 PASS（无回归）
```

- [ ] **Step 5: 提交**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && git add agent/prompt.py agent/loop.py tools/__init__.py && git commit -m "feat: 注入技能系统到系统提示词和 AgentLoop 初始化"
```

---

### Task 5: end-to-end 冒烟测试

**Files:**
- Create: 临时验证，手动测试

- [ ] **Step 1: 创建测试技能**

```bash
mkdir -p workspace/skills/dev/python-testing && cat > workspace/skills/dev/python-testing/SKILL.md << 'EOF'
---
name: python-testing
description: "Use when writing Python tests with pytest. Covers fixtures, mocking, and assertions."
category: dev
created_at: 2026-05-24
updated_at: 2026-05-24
---
# Python Testing

## When to Use
When the user asks to write or fix Python tests.

## Instructions
- Use pytest as the test framework
- Write test functions prefixed with `test_`
- Use `assert` for assertions, not unittest methods
- Mock external dependencies with `unittest.mock`
- Run tests with `python3 -m pytest`
EOF
```

- [ ] **Step 2: 验证技能加载进系统提示词**

```bash
source .venv/bin/activate && python3 -c "
from config.settings import load_config
from agent.prompt import build_system_prompt
config = load_config()
prompt = build_system_prompt(include_tools=True, include_skills=True, skills_dir=config.skills_dir)
assert 'python-testing' in prompt
assert 'Use when writing Python tests' in prompt
print('OK: 技能已注入系统提示词')
"
```

- [ ] **Step 3: 验证工具已注册**

```bash
source .venv/bin/activate && python3 -c "
import tools.skill
from tools.registry import registry
names = [d['function']['name'] for d in registry.get_definitions()]
assert 'skills_list' in names
assert 'skill_view' in names
assert 'skill_manage' in names
print('OK: 技能工具已注册')
"
```

- [ ] **Step 4: 验证 skill_view 加载技能内容**

```bash
source .venv/bin/activate && python3 -c "
import json
from pathlib import Path
from tools.skill import set_skills_dir, handle_skill_view
set_skills_dir(Path('workspace/skills'))
result = json.loads(handle_skill_view({'name': 'python-testing'}))
assert 'body' in result
assert 'pytest' in result['body']
print('OK: skill_view 正常加载')
"
```

- [ ] **Step 5: 清理测试技能**

```bash
rm -rf workspace/skills/dev
```

- [ ] **Step 6: 提交**

```bash
cd /Users/wangdeyu/Desktop/agent/F-Agent && git add -A && git status
```

（确认无意外文件后提交）

- [ ] **Step 7: 运行全部测试**

```bash
source .venv/bin/activate && python3 -m pytest tests/ -v
Expected: 全部 PASS
```

---

## 实现顺序

```
Task 1 (skill_utils.py) → Task 2 (loader.py) → Task 3 (tools/skill.py) → Task 4 (prompt.py/loop.py 集成) → Task 5 (冒烟验证)
```

依赖关系：Task 2 依赖 Task 1，Task 3 依赖 Task 1+2，Task 4 依赖 Task 3。