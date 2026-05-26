"""Skills Hub 工具：从外部源安装技能"""

import hashlib
import json
import logging
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
            "error": f"不支持的 source: {source}，可用: github, url"
        }, ensure_ascii=False)

    if not identifier:
        return json.dumps({"error": "identifier is required"}, ensure_ascii=False)

    # --- Check lock.json before API calls ---
    lock = _load_lock()
    for installed_name, installed_info in lock.get("installed", {}).items():
        if isinstance(installed_info, dict) and installed_info.get("identifier") == identifier:
            return json.dumps({
                "error": f"技能已安装(lock.json): {installed_name}",
                "hint": "如需重新安装，请先手动删除该技能"
            }, ensure_ascii=False)

    # --- Fetch files ---
    files: list[tuple[str, str]] = []

    try:
        if source == "github":
            from config.settings import load_config
            config = load_config()
            token = config.skills_hub.github_token

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

    meta, _ = parse_frontmatter(skill_md_content)
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

    # 2. Check lock.json by name (belt-and-suspenders)
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