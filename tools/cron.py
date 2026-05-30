"""Cron tool for creating and managing scheduled Agent prompts."""

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Callable, Any

from config.settings import get_config
from cron.models import JOB_ACTIVE, JOB_PAUSED
from cron.parser import parse_schedule
from cron.store import CronStore
from db.session import SessionDB
from tools.registry import registry

CronConfirmCallback = Callable[[dict], bool]

logger = logging.getLogger(__name__)

_confirm_callback: ContextVar[CronConfirmCallback | None] = ContextVar("cron_confirm_callback", default=None)
_store: ContextVar[CronStore | None] = ContextVar("cron_store", default=None)
_session_db: ContextVar[SessionDB | None] = ContextVar("cron_session_db", default=None)
_owns_store: ContextVar[bool] = ContextVar("cron_owns_store", default=False)


def set_cron_confirm_callback(callback: CronConfirmCallback | None) -> None:
    """Set or clear the callback used to confirm cron job creation."""
    _confirm_callback.set(callback)


def _close_internal_store() -> None:
    session_db = _session_db.get()
    if _owns_store.get() and session_db is not None:
        session_db.close()
    _session_db.set(None)
    _owns_store.set(False)


def set_cron_store(store: CronStore | None) -> None:
    """Set or clear the CronStore override used by tests or CLI integration."""
    _close_internal_store()
    _store.set(store)
    _owns_store.set(False)


def _get_store() -> CronStore:
    store = _store.get()
    if store is None:
        session_db = SessionDB(get_config().db_path)
        store = CronStore(session_db.conn)
        _session_db.set(session_db)
        _store.set(store)
        _owns_store.set(True)
    return store


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _error(message: str) -> str:
    return _json({"ok": False, "error": message})


def _require_str(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def _datetime_to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _job_to_dict(job: Any) -> dict[str, Any]:
    if isinstance(job, dict):
        data = dict(job)
    else:
        data = dict(vars(job))
    return {key: _datetime_to_iso(value) for key, value in data.items()}


def _create(args: dict, now: datetime) -> str:
    name = _require_str(args, "name")
    prompt = _require_str(args, "prompt")
    schedule = _require_str(args, "schedule")
    allowed_dangerous_keys = args.get("allowed_dangerous_keys", [])
    if allowed_dangerous_keys is None:
        allowed_dangerous_keys = []
    if not isinstance(allowed_dangerous_keys, list) or not all(isinstance(key, str) for key in allowed_dangerous_keys):
        raise ValueError("allowed_dangerous_keys must be a list of strings")

    parsed = parse_schedule(schedule, now=now)
    payload = {
        "action": "create",
        "name": name,
        "prompt": prompt,
        "schedule": schedule,
        "schedule_type": parsed.schedule_type,
        "next_run_at": parsed.next_run_at.isoformat(),
        "allowed_dangerous_keys": allowed_dangerous_keys,
    }

    confirm_callback = _confirm_callback.get()
    if confirm_callback is None:
        return _error("cron confirmation callback is not configured")
    if not confirm_callback(payload):
        return _json({"ok": False, "cancelled": True})

    job = _get_store().create_job(
        job_id=str(uuid.uuid4()),
        name=name,
        prompt=prompt,
        parsed=parsed,
        allowed_dangerous_keys=allowed_dangerous_keys,
        now=now,
    )
    return _json({"ok": True, "job": _job_to_dict(job)})


def _list() -> str:
    jobs = [_job_to_dict(job) for job in _get_store().list_jobs()]
    return _json({"ok": True, "jobs": jobs})


def _pause(args: dict, now: datetime) -> str:
    job_id = _require_str(args, "job_id")
    _get_store().update_job_state(job_id, JOB_PAUSED, now=now)
    return _json({"ok": True, "job_id": job_id, "state": JOB_PAUSED})


def _resume(args: dict, now: datetime) -> str:
    job_id = _require_str(args, "job_id")
    _get_store().update_job_state(job_id, JOB_ACTIVE, now=now)
    return _json({"ok": True, "job_id": job_id, "state": JOB_ACTIVE})


def _remove(args: dict) -> str:
    job_id = _require_str(args, "job_id")
    _get_store().delete_job(job_id)
    return _json({"ok": True, "job_id": job_id, "removed": True})


def run_cron_tool(args: Any) -> str:
    """Create, list, pause, resume, or remove scheduled Agent prompts."""
    try:
        if not isinstance(args, dict):
            raise ValueError("args must be a dict")
        action = _require_str(args, "action")
        now = datetime.now().astimezone()
        if action == "create":
            return _create(args, now)
        if action == "list":
            return _list()
        if action == "pause":
            return _pause(args, now)
        if action == "resume":
            return _resume(args, now)
        if action == "remove":
            return _remove(args)
        raise ValueError(f"unknown action: {action}")
    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.exception("Cron tool failed")
        return _error(str(exc))


registry.register(
    name="cron",
    schema={
        "type": "function",
        "function": {
            "name": "cron",
            "description": (
                "创建、查看、暂停、恢复、删除定时 Agent prompt。"
                "创建前必须经过用户确认；本工具不支持自然语言时间，LLM 应先转换为 "
                "10m、every 1h、ISO 时间或 5 字段 cron 表达式。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "pause", "resume", "remove"],
                        "description": "操作类型：create/list/pause/resume/remove。",
                    },
                    "name": {"type": "string", "description": "定时任务名称，create 必填。"},
                    "prompt": {"type": "string", "description": "要定时执行的 Agent prompt，create 必填。"},
                    "schedule": {
                        "type": "string",
                        "description": "调度表达式，create 必填；支持 10m、every 1h、ISO 时间或 5 字段 cron。",
                    },
                    "allowed_dangerous_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "允许本定时任务使用的危险操作授权键列表，create 可选。",
                    },
                    "job_id": {"type": "string", "description": "任务 ID，pause/resume/remove 必填。"},
                },
                "required": ["action"],
            },
        },
    },
    handler=run_cron_tool,
)
