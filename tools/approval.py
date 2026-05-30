"""命令审批模块：危险检测 + 会话状态 + 回调机制"""

import re
import threading
from contextvars import ContextVar
from typing import Callable

ApprovalCallback = Callable[[str, str, str], str]

# ============================================================
# Pattern definitions  (regex, key, description)
# ============================================================

HARDLINE_PATTERNS: list[tuple[str, str, str]] = [
    (r"rm\s+-rf\s+(/(?:\s|$|--)|/home|/etc|/root|/boot|/var|/usr|/opt|/sys|/proc|/dev)", "rm_system", "删除系统关键目录"),
    (r"sudo\s+rm\s+-rf\s+(/(?:\s|$|--)|/home|/etc|/root)", "sudo_rm_system", "sudo 删除系统关键目录"),
    (r"mkfs\.?\w*\s+/dev/", "mkfs", "格式化磁盘设备"),
    (r"mkfs(/[\w.]+)?\s+/dev/", "mkfs", "格式化磁盘设备"),
    (r"dd\s+.*of=/dev/sd", "dd_raw", "直接写入块设备"),
    (r":\(\)\{\s*:\s*\|:\s*&\s*\};:", "fork_bomb", "Fork 炸弹"),
    (r"kill\s+-9\s+-1\b", "kill_all", "终止所有进程"),
    (r"killall\s+-9\b", "killall", "强制终止所有进程"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "shutdown", "系统关机/重启"),
    (r">\s*/etc/(passwd|shadow|sudoers|fstab)", "overwrite_system", "覆盖系统关键文件"),
    (r"chmod\s+-R\s+777\s+(/|/etc|/home|/var|/usr)", "chmod777_system", "批量放开系统权限"),
    (r"dd\s+if=/dev/zero\s+of=/dev/", "dd_zero", "磁盘清零"),
    (r"chown\s+-R\s+\S+\s+(/|/etc|/var|/usr|/home)", "chown_system", "批量更改系统文件属主"),
    (r"format\s+[cC]:", "format_c", "格式化 Windows 系统盘"),
]

DANGEROUS_PATTERNS: list[tuple[str, str, str]] = [
    (r"rm\s+-rf\s", "rm_rf", "递归强制删除"),
    (r"rm\s+-r\s", "rm_r", "递归删除"),
    (r"chmod\s+777\s", "chmod777", "设置 777 权限"),
    (r"chmod\s+-R\s", "chmod_r", "递归修改权限"),
    (r"chown\s+-R\s", "chown_r", "递归修改文件属主"),
    (r"git\s+push\s+--force", "git_push_force", "强制推送"),
    (r"git\s+push\s+-f\b", "git_push_force", "强制推送"),
    (r"git\s+reset\s+--hard", "git_reset_hard", "硬重置 Git"),
    (r"curl\s+\S+\s*\|\s*(ba)?sh", "curl_pipe_sh", "curl 管道执行脚本"),
    (r"wget\s+\S+\s+-O\s+-\s*\|\s*(ba)?sh", "wget_pipe_sh", "wget 管道执行脚本"),
    (r"pip\s+uninstall\s", "pip_uninstall", "卸载 Python 包"),
    (r"npm\s+uninstall\s", "npm_uninstall", "卸载 npm 包"),
    (r"DROP\s+(TABLE|DATABASE)", "drop_table", "删除数据库表/库"),
    (r"TRUNCATE\s+(TABLE\s+)?\w", "truncate", "清空数据库表"),
    (r"docker\s+rm\s", "docker_rm", "删除 Docker 容器"),
    (r"docker\s+rmi\s", "docker_rmi", "删除 Docker 镜像"),
    (r"docker\s+system\s+prune", "docker_prune", "清理 Docker 系统"),
    (r"docker\s+volume\s+rm", "docker_volume_rm", "删除 Docker 卷"),
    (r">\s*/etc/", "redirect_etc", "重定向覆盖系统文件"),
    (r"del\s+/[fq]\s+/s", "del_force", "Windows 强制递归删除"),
]

# ============================================================
# Eager-compiled patterns
# ============================================================

_hardline_compiled: list[tuple[re.Pattern, str, str]] = [
    (re.compile(p, re.IGNORECASE), k, d) for p, k, d in HARDLINE_PATTERNS
]
_dangerous_compiled: list[tuple[re.Pattern, str, str]] = [
    (re.compile(p, re.IGNORECASE), k, d) for p, k, d in DANGEROUS_PATTERNS
]

# ============================================================
# Global state (thread-safe)
# ============================================================

_UNSET = object()

_approval_callback: ContextVar[ApprovalCallback | None] = ContextVar("approval_callback", default=None)
_approval_mode: ContextVar[str] = ContextVar("approval_mode", default="manual")
_approval_session_id: ContextVar[str | None] = ContextVar("approval_session_id", default=None)
_allowed_dangerous_keys: ContextVar[frozenset[str]] = ContextVar("allowed_dangerous_keys", default=frozenset())
_session_approved: dict[str, set[str]] = {}
_lock = threading.Lock()


def set_approval_callback(callback: ApprovalCallback | None) -> None:
    """注册审批回调，由 CLI 层在初始化时调用。"""
    _approval_callback.set(callback)


def _get_approval_callback() -> ApprovalCallback | None:
    return _approval_callback.get()


def set_approval_context(
    mode: str | object = _UNSET,
    session_id: str | None | object = _UNSET,
    allowed_dangerous_keys: list[str] | None | object = _UNSET,
) -> None:
    """设置审批上下文，在每个 Agent 运行前调用。"""
    if mode is _UNSET and session_id is _UNSET and allowed_dangerous_keys is _UNSET:
        _approval_mode.set("manual")
        _approval_session_id.set(None)
        _allowed_dangerous_keys.set(frozenset())
        return

    if isinstance(mode, str):
        _approval_mode.set(mode)
    if session_id is None or isinstance(session_id, str):
        _approval_session_id.set(session_id)
    if allowed_dangerous_keys is None:
        _allowed_dangerous_keys.set(frozenset())
    elif isinstance(allowed_dangerous_keys, list):
        _allowed_dangerous_keys.set(frozenset(allowed_dangerous_keys))


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
    cmd = _normalize_command(command)

    for pattern, key, description in _hardline_compiled:
        if pattern.search(cmd):
            return ("hardline", key, description)

    for pattern, key, description in _dangerous_compiled:
        if pattern.search(cmd):
            return ("dangerous", key, description)

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

    if key is None or description is None:
        return {
            "approved": False,
            "message": f"危险命令检测结果缺少授权信息\n命令: {command}",
            "status": "invalid_detection",
        }

    mode = _approval_mode.get()
    session_id = _approval_session_id.get()
    allowed_dangerous_keys = _allowed_dangerous_keys.get()

    if key in allowed_dangerous_keys:
        return {"approved": True, "message": "", "status": "cron_allowed"}

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
