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
