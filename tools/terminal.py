"""终端执行工具"""

import json
import subprocess

from tools.registry import registry


def run_terminal(args: dict) -> str:
    """执行终端命令

    Args:
        args: {"command": str, "timeout": int}

    Returns:
        命令输出（stdout + stderr）
    """
    command = args.get("command", "")
    timeout = args.get("timeout", 30)

    if not command:
        return json.dumps({"error": "No command provided"}, ensure_ascii=False)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        return json.dumps(output, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out after {timeout}s"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# 自注册
registry.register(
    name="terminal",
    schema={
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "在终端执行 shell 命令，返回 stdout、stderr 和退出码",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒），默认 30",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        },
    },
    handler=run_terminal,
    parallel_safe=False,
)
