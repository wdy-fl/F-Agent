from datetime import datetime, timezone

import pytest

from cron.parser import ScheduleParseError, compute_following_run, parse_schedule


BASE = datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)


def test_parse_delay_once_minutes():
    parsed = parse_schedule("10m", now=BASE)

    assert parsed.schedule_type == "once"
    assert parsed.interval_seconds == 600
    assert parsed.cron_expr is None
    assert parsed.next_run_at == datetime(2026, 5, 30, 10, 10, tzinfo=timezone.utc)


def test_parse_iso_once():
    parsed = parse_schedule("2026-05-31T09:00:00+00:00", now=BASE)

    assert parsed.schedule_type == "once"
    assert parsed.next_run_at == datetime(2026, 5, 31, 9, 0, tzinfo=timezone.utc)


def test_parse_naive_iso_uses_base_timezone():
    parsed = parse_schedule("2026-05-31T09:00:00", now=BASE)

    assert parsed.next_run_at == datetime(2026, 5, 31, 9, 0, tzinfo=timezone.utc)


def test_parse_schedule_rejects_naive_now():
    with pytest.raises(ScheduleParseError, match="now must be timezone-aware"):
        parse_schedule("10m", now=datetime(2026, 5, 30, 10, 0))


def test_parse_interval_hours():
    parsed = parse_schedule("every 2h", now=BASE)

    assert parsed.schedule_type == "interval"
    assert parsed.interval_seconds == 7200
    assert parsed.next_run_at == datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)


def test_parse_cron_expression():
    parsed = parse_schedule("0 9 * * *", now=BASE)

    assert parsed.schedule_type == "cron"
    assert parsed.cron_expr == "0 9 * * *"
    assert parsed.next_run_at == datetime(2026, 5, 31, 9, 0, tzinfo=timezone.utc)


def test_parse_rejects_non_standard_cron_expression():
    with pytest.raises(ScheduleParseError, match="Unsupported schedule"):
        parse_schedule("*/5 * * * * *", now=BASE)


def test_compute_following_interval_run():
    next_run = compute_following_run("interval", BASE, interval_seconds=3600)

    assert next_run == datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc)


def test_compute_following_run_rejects_naive_base():
    with pytest.raises(ScheduleParseError, match="base must be timezone-aware"):
        compute_following_run("interval", datetime(2026, 5, 30, 10, 0), interval_seconds=3600)


def test_invalid_schedule_raises_clear_error():
    with pytest.raises(ScheduleParseError, match="Unsupported schedule"):
        parse_schedule("tomorrow morning", now=BASE)
