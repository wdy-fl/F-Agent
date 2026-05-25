"""命令审批模块：危险检测 + 会话状态 + 回调机制"""

import re
import threading
from typing import Callable

ApprovalCallback = Callable[[str, str, str], str]

# ============================================================
# Pattern definitions
# ============================================================

HARDLINE_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+(/|/home|/etc|/root|/boot|/var|/usr|/opt|/sys|/proc|/dev)", "删除系统关键目录"),
    (r"sudo\s+rm\s+-rf\s+(/|/home|/etc|/root)", "sudo 删除系统关键目录"),
    (r"mkfs\.?\w*\s+/dev/", "格式化磁盘设备"),
    (r"mkfs(/[\w.]+)?\s+/dev/", "格式化磁盘设备"),
    (r"dd\s+.*of=/dev/sd", "直接写入块设备"),
    (r":\(\)\{\s*:\s*\|:\s*&\s*\};:", "Fork 炸弹"),
    (r"kill\s+-9\s+-1\b", "终止所有进程"),
    (r"killall\s+-9\b", "强制终止所有进程"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "系统关机/重启"),
    (r">\s*/etc/(passwd|shadow|sudoers|fstab)", "覆盖系统关键文件"),
    (r"chmod\s+-R\s+777\s+(/|/etc|/home|/var|/usr)", "批量放开系统权限"),
    (r"dd\s+if=/dev/zero\s+of=/dev/", "磁盘清零"),
    (r"chown\s+-R\s+\S+\s+(/|/etc|/var|/usr|/home)", "批量更改系统文件属主"),
    (r"format\s+[cC]:", "格式化 Windows 系统盘"),
]

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s", "递归强制删除"),
    (r"rm\s+-r\s", "递归删除"),
    (r"chmod\s+777\s", "设置 777 权限"),
    (r"chmod\s+-R\s", "递归修改权限"),
    (r"chown\s+-R\s", "递归修改文件属主"),
    (r"git\s+push\s+--force", "强制推送"),
    (r"git\s+push\s+-f\b", "强制推送"),
    (r"git\s+reset\s+--hard", "硬重置 Git"),
    (r"curl\s+\S+\s*\|\s*(ba)?sh", "curl 管道执行脚本"),
    (r"wget\s+\S+\s+-O\s+-\s*\|\s*(ba)?sh", "wget 管道执行脚本"),
    (r"pip\s+uninstall\s", "卸载 Python 包"),
    (r"npm\s+uninstall\s", "卸载 npm 包"),
    (r"DROP\s+(TABLE|DATABASE)", "删除数据库表/库"),
    (r"TRUNCATE\s+(TABLE\s+)?\w", "清空数据库表"),
    (r"docker\s+rm\s", "删除 Docker 容器"),
    (r"docker\s+rmi\s", "删除 Docker 镜像"),
    (r"docker\s+system\s+prune", "清理 Docker 系统"),
    (r"docker\s+volume\s+rm", "删除 Docker 卷"),
    (r">\s*/etc/", "重定向覆盖系统文件"),
    (r"del\s+/[fq]\s+/s", "Windows 强制递归删除"),
]

# ============================================================
# Lazy-compiled patterns
# ============================================================

_hardline_compiled: list[tuple[re.Pattern, str]] = []
_dangerous_compiled: list[tuple[re.Pattern, str]] = []
_patterns_compiled: bool = False


def _compile_patterns() -> None:
    global _hardline_compiled, _dangerous_compiled, _patterns_compiled
    if _patterns_compiled:
        return
    _hardline_compiled = [(re.compile(p, re.IGNORECASE), d) for p, d in HARDLINE_PATTERNS]
    _dangerous_compiled = [(re.compile(p, re.IGNORECASE), d) for p, d in DANGEROUS_PATTERNS]
    _patterns_compiled = True


# ============================================================
# Global state (thread-safe)
# ============================================================

_approval_callback: ApprovalCallback | None = None
_approval_mode: str = "manual"
_approval_session_id: str | None = None
_session_approved: dict[str, set[str]] = {}
_lock = threading.Lock()


def set_approval_callback(callback: ApprovalCallback | None) -> None:
    """注册审批回调，由 CLI 层在初始化时调用。"""
    global _approval_callback
    with _lock:
        _approval_callback = callback


def _get_approval_callback() -> ApprovalCallback | None:
    with _lock:
        return _approval_callback


def set_approval_context(mode: str = "manual", session_id: str | None = None) -> None:
    """设置审批上下文，在每个 Agent 运行前调用。"""
    global _approval_mode, _approval_session_id
    with _lock:
        _approval_mode = mode
        _approval_session_id = session_id


def _normalize_command(command: str) -> str:
    """规范化命令用于模式匹配。"""
    cmd = " ".join(command.split())
    cmd = re.sub(r'^(cd\s+\S+\s*(?:&&|;)\s*)', '', cmd)
    return cmd


# ============================================================
# Public API
# ============================================================

def detect_dangerous_command(command: str) -> tuple[str | None, str | None, str | None]:
    """检测命令的危险级别。

    Returns:
        (level, key, description) — level 为 "hardline"、"dangerous" 或 None
    """
    _compile_patterns()
    cmd = _normalize_command(command)

    for pattern, description in _hardline_compiled:
        if pattern.search(cmd):
            return ("hardline", description, description)

    for pattern, description in _dangerous_compiled:
        if pattern.search(cmd):
            return ("dangerous", description, description)

    return (None, None, None)


def check_all_guards(command: str) -> dict:
    """检查命令是否需要审批。

    Returns:
        {"approved": bool, "message": str, "status": str}
    """
    level, key, description = detect_dangerous_command(command)

    if level == "hardline":
        return {
            "approved": False,
            "message": f"命令被阻止: {description}\n命令: {command}",
            "status": "hardline",
        }

    if level is None:
        return {"approved": True, "message": "", "status": "safe"}

    with _lock:
        mode = _approval_mode
        session_id = _approval_session_id

    if mode == "off":
        return {"approved": True, "message": "", "status": "bypass"}

    if session_id and key:
        with _lock:
            if session_id in _session_approved and key in _session_approved[session_id]:
                return {"approved": True, "message": "", "status": "session_remembered"}

    callback = _get_approval_callback()
    if not callback:
        return {
            "approved": False,
            "message": f"危险命令需要审批但回调未注册: {description}\n命令: {command}",
            "status": "no_callback",
        }

    choice = callback(command, description, key)

    if choice == "session" and session_id and key:
        with _lock:
            if session_id not in _session_approved:
                _session_approved[session_id] = set()
            _session_approved[session_id].add(key)
        return {"approved": True, "message": "", "status": "session_remembered"}

    if choice == "once":
        return {"approved": True, "message": "", "status": "approved_once"}

    return {"approved": False, "message": "用户拒绝了该命令", "status": "denied"}
