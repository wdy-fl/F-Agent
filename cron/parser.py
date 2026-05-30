import re
from datetime import datetime, timedelta

from croniter import croniter

from cron.models import SCHEDULE_CRON, SCHEDULE_INTERVAL, SCHEDULE_ONCE, ParsedSchedule

_DURATION_RE = re.compile(r"^(?P<amount>\d+)(?P<unit>[mhd])$")
_INTERVAL_RE = re.compile(r"^every\s+(?P<amount>\d+)(?P<unit>[mhd])$", re.IGNORECASE)


class ScheduleParseError(ValueError):
    pass


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _seconds(amount: int, unit: str) -> int:
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 3600
    if unit == "d":
        return amount * 86400
    raise ScheduleParseError(f"Unsupported duration unit: {unit}")


def parse_schedule(expr: str, now: datetime | None = None) -> ParsedSchedule:
    if now is None:
        base = datetime.now().astimezone()
    else:
        if not _is_timezone_aware(now):
            raise ScheduleParseError("now must be timezone-aware")
        base = now
    value = expr.strip()

    delay = _DURATION_RE.match(value)
    if delay:
        interval_seconds = _seconds(int(delay.group("amount")), delay.group("unit"))
        return ParsedSchedule(
            schedule_expr=value,
            schedule_type=SCHEDULE_ONCE,
            interval_seconds=interval_seconds,
            next_run_at=base + timedelta(seconds=interval_seconds),
        )

    interval = _INTERVAL_RE.match(value)
    if interval:
        interval_seconds = _seconds(int(interval.group("amount")), interval.group("unit").lower())
        return ParsedSchedule(
            schedule_expr=value,
            schedule_type=SCHEDULE_INTERVAL,
            interval_seconds=interval_seconds,
            next_run_at=base + timedelta(seconds=interval_seconds),
        )

    try:
        absolute = datetime.fromisoformat(value)
    except ValueError:
        absolute = None
    if absolute is not None:
        if not _is_timezone_aware(absolute):
            absolute = absolute.replace(tzinfo=base.tzinfo)
        return ParsedSchedule(
            schedule_expr=value,
            schedule_type=SCHEDULE_ONCE,
            next_run_at=absolute,
        )

    if len(value.split()) == 5 and croniter.is_valid(value):
        return ParsedSchedule(
            schedule_expr=value,
            schedule_type=SCHEDULE_CRON,
            cron_expr=value,
            next_run_at=croniter(value, base).get_next(datetime),
        )

    raise ScheduleParseError(f"Unsupported schedule: {expr}")


def compute_following_run(
    schedule_type: str,
    base: datetime,
    *,
    interval_seconds: int | None = None,
    cron_expr: str | None = None,
) -> datetime | None:
    if not _is_timezone_aware(base):
        raise ScheduleParseError("base must be timezone-aware")
    if schedule_type == SCHEDULE_ONCE:
        return None
    if schedule_type == SCHEDULE_INTERVAL:
        if interval_seconds is None:
            raise ScheduleParseError("interval_seconds is required for interval schedule")
        return base + timedelta(seconds=interval_seconds)
    if schedule_type == SCHEDULE_CRON:
        if not cron_expr:
            raise ScheduleParseError("cron_expr is required for cron schedule")
        return croniter(cron_expr, base).get_next(datetime)
    raise ScheduleParseError(f"Unsupported schedule type: {schedule_type}")
