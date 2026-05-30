from dataclasses import dataclass
from datetime import datetime

JOB_ACTIVE = "active"
JOB_PAUSED = "paused"
JOB_DISABLED = "disabled"
JOB_MISSED = "missed"

RUN_SUCCESS = "success"
RUN_FAILED = "failed"
RUN_MISSED = "missed"

SCHEDULE_ONCE = "once"
SCHEDULE_INTERVAL = "interval"
SCHEDULE_CRON = "cron"


@dataclass(frozen=True)
class ParsedSchedule:
    schedule_expr: str
    schedule_type: str
    next_run_at: datetime
    interval_seconds: int | None = None
    cron_expr: str | None = None


@dataclass(frozen=True)
class CronJob:
    id: str
    name: str
    prompt: str
    schedule_expr: str
    schedule_type: str
    next_run_at: datetime | None
    state: str
    allowed_dangerous_keys: list[str]
    created_at: datetime
    updated_at: datetime
    interval_seconds: int | None = None
    cron_expr: str | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class CronRun:
    id: str
    job_id: str
    scheduled_at: datetime
    status: str
    session_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: str | None = None
    error: str | None = None
