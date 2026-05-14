"""文件操作工具：读文件、写文件、列目录"""

import json
from pathlib import Path

from tools.registry import registry


def read_file(args: dict) -> str:
    """读取文件内容

    Args:
        args: {"path": str, "offset": int, "limit": int}

    Returns:
        文件内容
    """
    path = args.get("path", "")
    offset = args.get("offset", 0)
    limit = args.get("limit", 2000)

    if not path:
        return json.dumps({"error": "No path provided"}, ensure_ascii=False)

    try:
        p = Path(path).expanduser()
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"}, ensure_ascii=False)
        if not p.is_file():
            return json.dumps({"error": f"Not a file: {path}"}, ensure_ascii=False)

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        selected = lines[offset:offset + limit]
        content = "".join(selected)

        return json.dumps({
            "path": str(p),
            "content": content,
            "total_lines": total_lines,
            "showing": f"lines {offset + 1}-{min(offset + limit, total_lines)}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def write_file(args: dict) -> str:
    """写入文件内容

    Args:
        args: {"path": str, "content": str, "append": bool}

    Returns:
        操作结果
    """
    path = args.get("path", "")
    content = args.get("content", "")
    append = args.get("append", False)

    if not path:
        return json.dumps({"error": "No path provided"}, ensure_ascii=False)

    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)

        return json.dumps({
            "path": str(p),
            "action": "appended" if append else "written",
            "bytes": len(content.encode("utf-8")),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def list_files(args: dict) -> str:
    """列出目录内容

    Args:
        args: {"path": str, "pattern": str}

    Returns:
        目录内容列表
    """
    path = args.get("path", ".")
    pattern = args.get("pattern", "*")

    try:
        p = Path(path).expanduser()
        if not p.exists():
            return json.dumps({"error": f"Directory not found: {path}"}, ensure_ascii=False)
        if not p.is_dir():
            return json.dumps({"error": f"Not a directory: {path}"}, ensure_ascii=False)

        entries = []
        for entry in sorted(p.glob(pattern)):
            entries.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })

        return json.dumps({
            "path": str(p),
            "entries": entries,
            "count": len(entries),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# 自注册
registry.register(
    name="read_file",
    schema={
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容，支持指定行范围",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "offset": {"type": "integer", "description": "起始行号（0-based），默认 0", "default": 0},
                    "limit": {"type": "integer", "description": "最大读取行数，默认 2000", "default": 2000},
                },
                "required": ["path"],
            },
        },
    },
    handler=read_file,
    parallel_safe=True,
)

registry.register(
    name="write_file",
    schema={
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入文件内容，可覆盖或追加",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"},
                    "append": {"type": "boolean", "description": "是否追加模式，默认覆盖", "default": False},
                },
                "required": ["path", "content"],
            },
        },
    },
    handler=write_file,
    parallel_safe=False,
)

registry.register(
    name="list_files",
    schema={
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出目录下的文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径，默认当前目录", "default": "."},
                    "pattern": {"type": "string", "description": "glob 匹配模式，默认 *", "default": "*"},
                },
                "required": [],
            },
        },
    },
    handler=list_files,
    parallel_safe=True,
)
