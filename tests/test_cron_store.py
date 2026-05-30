from datetime import datetime, timedelta, timezone

import pytest

from cron.models import JOB_ACTIVE, JOB_PAUSED, RUN_FAILED, RUN_SUCCESS, ParsedSchedule
from cron.store import CronStore
from db.session import SessionDB


BASE = datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)


def make_store(tmp_path):
    db = SessionDB(tmp_path / "test.db")
    return db, CronStore(db.conn)


def parsed(expr="every 1h", next_run_at=None):
    return ParsedSchedule(
        schedule_expr=expr,
        schedule_type="interval",
        next_run_at=next_run_at or datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc),
        interval_seconds=3600,
    )


def test_create_get_job_roundtrips_fields_and_allowed_keys(tmp_path):
    db, store = make_store(tmp_path)
    try:
        job = store.create_job(
            "job-1",
            "daily summary",
            "summarize workspace",
            parsed(),
            allowed_dangerous_keys=["Bash(git status)", "Read(/tmp/a)"],
            now=BASE,
        )

        assert job.id == "job-1"
        assert job.name == "daily summary"
        assert job.prompt == "summarize workspace"
        assert job.schedule_expr == "every 1h"
        assert job.schedule_type == "interval"
        assert job.interval_seconds == 3600
        assert job.cron_expr is None
        assert job.next_run_at == datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc)
        assert job.state == JOB_ACTIVE
        assert job.allowed_dangerous_keys == ["Bash(git status)", "Read(/tmp/a)"]
        assert job.created_at == BASE
        assert job.updated_at == BASE
        assert job.last_run_at is None
        assert job.last_status is None
        assert job.last_error is None

        fetched = store.get_job("job-1")
        assert fetched == job
    finally:
        db.close()


def test_list_jobs_returns_created_order(tmp_path):
    db, store = make_store(tmp_path)
    try:
        store.create_job("job-2", "second", "prompt", parsed(), now=BASE.replace(hour=12))
        store.create_job("job-1", "first", "prompt", parsed(), now=BASE.replace(hour=11))

        assert [job.id for job in store.list_jobs()] == ["job-1", "job-2"]
    finally:
        db.close()


def test_list_due_jobs_returns_only_active_due_jobs_in_next_run_order(tmp_path):
    db, store = make_store(tmp_path)
    try:
        now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        store.create_job("future", "future", "prompt", parsed(next_run_at=now.replace(hour=13)), now=BASE)
        store.create_job("paused", "paused", "prompt", parsed(next_run_at=now.replace(hour=10)), state=JOB_PAUSED, now=BASE)
        store.create_job("due-later", "due later", "prompt", parsed(next_run_at=now.replace(hour=11)), now=BASE)
        store.create_job("due-earlier", "due earlier", "prompt", parsed(next_run_at=now.replace(hour=9)), now=BASE)

        assert [job.id for job in store.list_due_jobs(now)] == ["due-earlier", "due-later"]
    finally:
        db.close()


def test_list_due_jobs_normalizes_mixed_offsets_before_due_filtering_and_ordering(tmp_path):
    db, store = make_store(tmp_path)
    try:
        now = datetime(2026, 5, 30, 3, 0, tzinfo=timezone.utc)
        offset_8 = timezone(timedelta(hours=8))
        store.create_job(
            "job-a",
            "A",
            "prompt",
            parsed(next_run_at=datetime(2026, 5, 30, 10, 0, tzinfo=offset_8)),
            now=BASE,
        )
        store.create_job(
            "job-b",
            "B",
            "prompt",
            parsed(next_run_at=datetime(2026, 5, 30, 2, 30, tzinfo=timezone.utc)),
            now=BASE,
        )
        store.create_job(
            "job-c",
            "C",
            "prompt",
            parsed(next_run_at=datetime(2026, 5, 30, 12, 0, tzinfo=offset_8)),
            now=BASE,
        )

        due_jobs = store.list_due_jobs(now)

        assert [job.id for job in due_jobs] == ["job-a", "job-b"]
        assert [job.next_run_at for job in due_jobs] == [
            datetime(2026, 5, 30, 2, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 2, 30, tzinfo=timezone.utc),
        ]
    finally:
        db.close()


def test_create_job_rejects_naive_next_run_at(tmp_path):
    db, store = make_store(tmp_path)
    try:
        with pytest.raises(ValueError, match="timezone-aware"):
            store.create_job(
                "job-1",
                "job",
                "prompt",
                parsed(next_run_at=datetime(2026, 5, 30, 11, 0)),
                now=BASE,
            )
    finally:
        db.close()


def test_update_job_state_updates_state_and_timestamp(tmp_path):
    db, store = make_store(tmp_path)
    try:
        store.create_job("job-1", "job", "prompt", parsed(), now=BASE)
        updated_at = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)

        store.update_job_state("job-1", JOB_PAUSED, now=updated_at)

        job = store.get_job("job-1")
        assert job is not None
        assert job.state == JOB_PAUSED
        assert job.updated_at == updated_at
    finally:
        db.close()


def test_delete_job_cascades_runs(tmp_path):
    db, store = make_store(tmp_path)
    try:
        store.create_job("job-1", "job", "prompt", parsed(), now=BASE)
        store.create_run("run-1", "job-1", BASE, RUN_SUCCESS)

        store.delete_job("job-1")

        assert store.get_job("job-1") is None
        assert store.get_run("run-1") is None
        assert store.list_runs("job-1") == []
    finally:
        db.close()


def test_update_after_run_updates_run_summary_fields_and_optional_state(tmp_path):
    db, store = make_store(tmp_path)
    try:
        store.create_job("job-1", "job", "prompt", parsed(), now=BASE)
        last_run_at = datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc)
        next_run_at = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        updated_at = datetime(2026, 5, 30, 11, 1, tzinfo=timezone.utc)

        store.update_after_run(
            "job-1",
            next_run_at=next_run_at,
            last_run_at=last_run_at,
            last_status=RUN_FAILED,
            last_error="boom",
            state=JOB_PAUSED,
            now=updated_at,
        )

        job = store.get_job("job-1")
        assert job is not None
        assert job.next_run_at == next_run_at
        assert job.last_run_at == last_run_at
        assert job.last_status == RUN_FAILED
        assert job.last_error == "boom"
        assert job.state == JOB_PAUSED
        assert job.updated_at == updated_at
    finally:
        db.close()


def test_create_get_and_list_runs(tmp_path):
    db, store = make_store(tmp_path)
    try:
        store.create_job("job-1", "job", "prompt", parsed(), now=BASE)
        later = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        earlier = datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc)
        finished = datetime(2026, 5, 30, 11, 5, tzinfo=timezone.utc)

        run_later = store.create_run(
            "run-2",
            "job-1",
            later,
            RUN_FAILED,
            error="failed",
        )
        run_earlier = store.create_run(
            "run-1",
            "job-1",
            earlier,
            RUN_SUCCESS,
            session_id="session-1",
            started_at=earlier,
            finished_at=finished,
            summary="done",
        )

        assert run_later.id == "run-2"
        assert run_later.job_id == "job-1"
        assert run_later.scheduled_at == later
        assert run_later.status == RUN_FAILED
        assert run_later.error == "failed"
        assert store.get_run("run-1") == run_earlier
        assert store.get_run("missing") is None
        assert store.list_runs("job-1") == [run_earlier, run_later]
    finally:
        db.close()
