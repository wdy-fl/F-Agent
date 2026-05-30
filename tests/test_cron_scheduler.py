from datetime import datetime, timedelta, timezone

import pytest

from config.settings import CronConfig
from cron.models import JOB_ACTIVE, JOB_MISSED, RUN_SUCCESS, SCHEDULE_INTERVAL, CronJob, CronRun


BASE = datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, jobs=None):
        self.jobs = list(jobs or [])
        self.list_due_calls = []
        self.state_updates = []

    def list_due_jobs(self, now):
        self.list_due_calls.append(now)
        return list(self.jobs)

    def update_job_state(self, job_id, state, now=None):
        self.state_updates.append((job_id, state, now))


class FakeRunner:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = failures or {}

    def run_job(self, job, scheduled_at):
        self.calls.append((job.id, scheduled_at))
        if job.id in self.failures:
            raise self.failures[job.id]
        return CronRun(id=f"run-{job.id}", job_id=job.id, scheduled_at=scheduled_at, status=RUN_SUCCESS)


class FakeThread:
    created = []

    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon
        self.started = False
        self.join_calls = []
        self.alive = False
        FakeThread.created.append(self)

    def start(self):
        self.started = True
        self.alive = True

    def join(self, timeout=None):
        self.join_calls.append(timeout)

    def is_alive(self):
        return self.alive


class FakeStopEvent:
    def __init__(self, stop_after_waits=2):
        self.set_calls = 0
        self.wait_calls = []
        self.stop_after_waits = stop_after_waits

    def is_set(self):
        return self.set_calls >= self.stop_after_waits

    def set(self):
        self.set_calls = self.stop_after_waits

    def clear(self):
        self.set_calls = 0

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        self.set_calls += 1


class Clock:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        if not self.values:
            raise AssertionError("clock exhausted")
        return self.values.pop(0)


def make_job(**overrides):
    values = {
        "id": "job-1",
        "name": "job",
        "prompt": "run the task",
        "schedule_expr": "every 1h",
        "schedule_type": SCHEDULE_INTERVAL,
        "next_run_at": BASE,
        "state": JOB_ACTIVE,
        "allowed_dangerous_keys": [],
        "created_at": BASE - timedelta(hours=1),
        "updated_at": BASE - timedelta(hours=1),
        "interval_seconds": 3600,
        "cron_expr": None,
    }
    values.update(overrides)
    return CronJob(**values)


def test_tick_disabled_does_not_query_due_jobs():
    from cron.scheduler import CronScheduler

    store = FakeStore([make_job()])
    scheduler = CronScheduler(store, FakeRunner(), CronConfig(enabled=False), clock=lambda: BASE)

    scheduler.tick()

    assert store.list_due_calls == []


def test_tick_runs_due_jobs_serially_with_each_jobs_scheduled_at():
    from cron.scheduler import CronScheduler

    job1 = make_job(id="job-1", next_run_at=BASE - timedelta(minutes=2))
    job2 = make_job(id="job-2", next_run_at=BASE - timedelta(minutes=1))
    store = FakeStore([job1, job2])
    runner = FakeRunner()
    scheduler = CronScheduler(store, runner, CronConfig(grace_seconds=300), clock=lambda: BASE)

    scheduler.tick()

    assert store.list_due_calls == [BASE]
    assert runner.calls == [
        ("job-1", BASE - timedelta(minutes=2)),
        ("job-2", BASE - timedelta(minutes=1)),
    ]


def test_tick_marks_jobs_past_grace_as_missed_without_running_them():
    from cron.scheduler import CronScheduler

    missed_job = make_job(id="missed", next_run_at=BASE - timedelta(seconds=121))
    runnable_job = make_job(id="runnable", next_run_at=BASE - timedelta(seconds=120))
    store = FakeStore([missed_job, runnable_job])
    runner = FakeRunner()
    scheduler = CronScheduler(store, runner, CronConfig(grace_seconds=120), clock=lambda: BASE)

    scheduler.tick()

    assert store.state_updates == [("missed", JOB_MISSED, BASE)]
    assert runner.calls == [("runnable", BASE - timedelta(seconds=120))]


def test_tick_calls_completion_callback_after_successful_run():
    from cron.scheduler import CronScheduler

    job1 = make_job(id="job-1", next_run_at=BASE)
    job2 = make_job(id="job-2", next_run_at=BASE + timedelta(seconds=1))
    store = FakeStore([job1, job2])
    runner = FakeRunner()
    completions = []
    scheduler = CronScheduler(
        store,
        runner,
        CronConfig(grace_seconds=300),
        clock=lambda: BASE,
        completion_callback=lambda job, run: completions.append((job.id, run.job_id)),
    )

    scheduler.tick()

    assert completions == [("job-1", "job-1"), ("job-2", "job-2")]


def test_tick_completion_callback_exception_does_not_block_later_due_jobs(caplog):
    from cron.scheduler import CronScheduler

    job1 = make_job(id="job-1", next_run_at=BASE)
    job2 = make_job(id="job-2", next_run_at=BASE + timedelta(seconds=1))
    store = FakeStore([job1, job2])
    runner = FakeRunner()
    completions = []

    def callback(job, run):
        completions.append((job.id, run.job_id))
        if job.id == "job-1":
            raise RuntimeError("notify failed")

    scheduler = CronScheduler(
        store,
        runner,
        CronConfig(grace_seconds=300),
        clock=lambda: BASE,
        completion_callback=callback,
    )

    scheduler.tick()

    assert completions == [("job-1", "job-1"), ("job-2", "job-2")]
    assert "completion callback failed" in caplog.text


def test_tick_runner_exception_does_not_block_later_due_jobs(caplog):
    from cron.scheduler import CronScheduler

    job1 = make_job(id="job-1", next_run_at=BASE)
    job2 = make_job(id="job-2", next_run_at=BASE + timedelta(seconds=1))
    store = FakeStore([job1, job2])
    runner = FakeRunner(failures={"job-1": RuntimeError("boom")})
    scheduler = CronScheduler(store, runner, CronConfig(grace_seconds=300), clock=lambda: BASE)

    scheduler.tick()

    assert runner.calls == [("job-1", BASE), ("job-2", BASE + timedelta(seconds=1))]
    assert "job-1" in caplog.text



def test_tick_skips_naive_scheduled_job_and_runs_later_valid_job(caplog):
    from cron.scheduler import CronScheduler

    naive_job = make_job(id="naive", next_run_at=datetime(2026, 5, 30, 10, 0))
    valid_job = make_job(id="valid", next_run_at=BASE)
    store = FakeStore([naive_job, valid_job])
    runner = FakeRunner()
    scheduler = CronScheduler(store, runner, CronConfig(grace_seconds=300), clock=lambda: BASE)

    scheduler.tick()

    assert runner.calls == [("valid", BASE)]
    assert "naive" in caplog.text


def test_tick_rejects_naive_now():
    from cron.scheduler import CronScheduler

    scheduler = CronScheduler(FakeStore(), FakeRunner(), CronConfig(), clock=lambda: BASE)

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        scheduler.tick(datetime(2026, 5, 30, 10, 0))


def test_start_disabled_does_not_create_thread():
    from cron.scheduler import CronScheduler

    FakeThread.created = []
    scheduler = CronScheduler(
        FakeStore(),
        FakeRunner(),
        CronConfig(enabled=False),
        clock=lambda: BASE,
        thread_factory=FakeThread,
    )

    scheduler.start()

    assert FakeThread.created == []


def test_start_is_idempotent_and_stop_joins_then_allows_restart():
    from cron.scheduler import CronScheduler

    FakeThread.created = []
    scheduler = CronScheduler(
        FakeStore(),
        FakeRunner(),
        CronConfig(enabled=True, tick_interval_seconds=60),
        clock=lambda: BASE,
        thread_factory=FakeThread,
    )

    scheduler.start()
    scheduler.start()

    assert len(FakeThread.created) == 1
    first_thread = FakeThread.created[0]
    assert first_thread.daemon is True
    assert first_thread.started is True

    first_thread.alive = False
    scheduler.stop(timeout=1.5)

    assert scheduler._stop_event.is_set()
    assert first_thread.join_calls == [1.5]

    scheduler.start()

    assert len(FakeThread.created) == 2
    assert FakeThread.created[1].started is True
    assert not scheduler._stop_event.is_set()


def test_run_loop_continues_waiting_after_tick_exception():
    from cron.scheduler import CronScheduler

    stop_event = FakeStopEvent(stop_after_waits=2)
    scheduler = CronScheduler(
        FakeStore(),
        FakeRunner(),
        CronConfig(enabled=True, tick_interval_seconds=13),
        clock=lambda: BASE,
    )
    scheduler._stop_event = stop_event
    calls = []

    def flaky_tick():
        calls.append("tick")
        if len(calls) == 1:
            raise RuntimeError("tick failed")

    scheduler.tick = flaky_tick

    scheduler._run_loop()

    assert calls == ["tick", "tick"]
    assert stop_event.wait_calls == [13, 13]


def test_stop_keeps_alive_thread_reference_and_start_does_not_create_second_thread():
    from cron.scheduler import CronScheduler

    FakeThread.created = []
    scheduler = CronScheduler(
        FakeStore(),
        FakeRunner(),
        CronConfig(enabled=True, tick_interval_seconds=60),
        clock=lambda: BASE,
        thread_factory=FakeThread,
    )

    scheduler.start()
    first_thread = FakeThread.created[0]
    scheduler.stop(timeout=0.01)

    assert first_thread.join_calls == [0.01]
    assert scheduler._thread is first_thread

    scheduler.start()

    assert len(FakeThread.created) == 1


def test_start_replaces_dead_thread_reference():
    from cron.scheduler import CronScheduler

    FakeThread.created = []
    scheduler = CronScheduler(
        FakeStore(),
        FakeRunner(),
        CronConfig(enabled=True, tick_interval_seconds=60),
        clock=lambda: BASE,
        thread_factory=FakeThread,
    )
    dead_thread = FakeThread(target=lambda: None, daemon=True)
    dead_thread.started = True
    dead_thread.alive = False
    scheduler._thread = dead_thread

    scheduler.start()

    assert len(FakeThread.created) == 2
    assert scheduler._thread is FakeThread.created[1]
    assert scheduler._thread.started is True
