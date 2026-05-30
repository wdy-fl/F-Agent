import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from config.settings import AppConfig, ApprovalConfig, get_config, set_config
from tools.cron import set_cron_store
from cron.models import JOB_ACTIVE, RUN_FAILED, RUN_SUCCESS, SCHEDULE_INTERVAL, SCHEDULE_ONCE, CronJob


BASE = datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self):
        self.runs = []
        self.updates = []
        self.create_run_calls = 0
        self.update_exc = None

    def create_run(self, run_id, job_id, scheduled_at, status, **kwargs):
        self.create_run_calls += 1
        from cron.models import CronRun

        run = CronRun(
            id=run_id,
            job_id=job_id,
            scheduled_at=scheduled_at,
            status=status,
            session_id=kwargs.get("session_id"),
            started_at=kwargs.get("started_at"),
            finished_at=kwargs.get("finished_at"),
            summary=kwargs.get("summary"),
            error=kwargs.get("error"),
        )
        self.runs.append(run)
        return run

    def update_after_run(self, job_id, **kwargs):
        self.updates.append((job_id, kwargs))
        if self.update_exc is not None:
            raise self.update_exc


class FakeSessionDB:
    def __init__(self, exc=None):
        self.ended_sessions = []
        self.exc = exc

    def end_session(self, session_id):
        self.ended_sessions.append(session_id)
        if self.exc is not None:
            raise self.exc


class FakeAgent:
    def __init__(self, session_id="session-1", result="done", exc=None):
        self.session_id = None
        self._session_id = session_id
        self.result = result
        self.exc = exc
        self.prompts = []

    def run(self, prompt):
        self.prompts.append(prompt)
        self.session_id = self._session_id
        if self.exc is not None:
            raise self.exc
        return self.result


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
        "allowed_dangerous_keys": ["rm_rf"],
        "created_at": BASE - timedelta(hours=1),
        "updated_at": BASE - timedelta(hours=1),
        "interval_seconds": 3600,
        "cron_expr": None,
    }
    values.update(overrides)
    return CronJob(**values)


@pytest.fixture(autouse=True)
def reset_config():
    original = get_config()
    set_config(AppConfig(approval=ApprovalConfig(mode="off")))
    yield
    set_config(original)


def test_run_job_sets_cron_tool_store_for_background_agent_context():
    from cron.runner import CronRunner
    import tools.cron as cron_tool

    main_store = FakeStore()
    background_store = FakeStore()
    session_db = FakeSessionDB()
    set_cron_store(main_store)
    selected_store = []

    def agent_factory(**kwargs):
        selected_store.append(cron_tool._get_store())
        return FakeAgent(session_id="session-1", result="ok")

    runner = CronRunner(
        background_store,
        session_db,
        agent_factory=agent_factory,
        clock=Clock(
            datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
        ),
        id_factory=lambda: "run-1",
        approval_context_setter=lambda **kwargs: None,
    )

    runner.run_job(make_job(), BASE)

    assert selected_store == [background_store]
    assert cron_tool._get_store() is background_store


def test_success_run_creates_fresh_agent_records_success_updates_job_and_ends_session():
    from cron.runner import CronRunner

    store = FakeStore()
    session_db = FakeSessionDB()
    agents = []

    def agent_factory(**kwargs):
        assert kwargs["session_db"] is session_db
        assert "output_callback" in kwargs
        agent = FakeAgent(session_id=f"session-{len(agents) + 1}", result="summary")
        agents.append(agent)
        return agent

    approvals = []
    runner = CronRunner(
        store,
        session_db,
        agent_factory=agent_factory,
        clock=Clock(
            datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
        ),
        id_factory=lambda: "run-1",
        approval_context_setter=lambda **kwargs: approvals.append(kwargs),
    )

    run = runner.run_job(make_job(), BASE)

    assert len(agents) == 1
    assert agents[0].prompts == ["run the task"]
    assert run.id == "run-1"
    assert run.status == RUN_SUCCESS
    assert run.session_id == "session-1"
    assert run.started_at == datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc)
    assert run.finished_at == datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc)
    assert run.summary == "summary"
    assert session_db.ended_sessions == ["session-1"]
    assert store.updates == [
        (
            "job-1",
            {
                "next_run_at": datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc),
                "last_run_at": datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
                "last_status": RUN_SUCCESS,
                "last_error": None,
                "now": datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
            },
        )
    ]
    assert approvals[-1] == {}


def test_interval_next_run_is_based_on_scheduled_at_not_finished_at():
    from cron.runner import CronRunner

    store = FakeStore()
    runner = CronRunner(
        store,
        FakeSessionDB(),
        agent_factory=lambda **kwargs: FakeAgent(result="ok"),
        clock=Clock(
            datetime(2026, 5, 30, 10, 59, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 11, 10, tzinfo=timezone.utc),
        ),
        id_factory=lambda: "run-1",
        approval_context_setter=lambda **kwargs: None,
    )

    scheduled_at = datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)
    runner.run_job(make_job(interval_seconds=1800), scheduled_at)

    assert store.updates[0][1]["next_run_at"] == datetime(2026, 5, 30, 10, 30, tzinfo=timezone.utc)


def test_failed_agent_run_records_failed_run_preserves_next_run_and_does_not_raise():
    from cron.runner import CronRunner

    store = FakeStore()
    session_db = FakeSessionDB()
    job_next = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    runner = CronRunner(
        store,
        session_db,
        agent_factory=lambda **kwargs: FakeAgent(session_id="session-fail", exc=RuntimeError("boom")),
        clock=Clock(
            datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
        ),
        id_factory=lambda: "run-failed",
        approval_context_setter=lambda **kwargs: None,
    )

    run = runner.run_job(make_job(next_run_at=job_next), BASE)

    assert run.status == RUN_FAILED
    assert run.error == "boom"
    assert run.session_id == "session-fail"
    assert session_db.ended_sessions == ["session-fail"]
    assert store.updates == [
        (
            "job-1",
            {
                "next_run_at": job_next,
                "last_run_at": datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
                "last_status": RUN_FAILED,
                "last_error": "boom",
                "now": datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
            },
        )
    ]


def test_approval_context_uses_job_allowed_keys_binds_session_after_run_and_clears():
    from cron.runner import CronRunner

    approvals = []
    job = make_job(allowed_dangerous_keys=["rm_rf", "git_push_force"])
    runner = CronRunner(
        FakeStore(),
        FakeSessionDB(),
        agent_factory=lambda **kwargs: FakeAgent(session_id="cron-session", result="ok"),
        clock=Clock(
            datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
        ),
        id_factory=lambda: "run-1",
        approval_context_setter=lambda **kwargs: approvals.append(kwargs),
    )

    runner.run_job(job, BASE)

    assert approvals == [
        {"mode": "off", "session_id": None, "allowed_dangerous_keys": ["rm_rf", "git_push_force"]},
        {"mode": "off", "session_id": "cron-session", "allowed_dangerous_keys": ["rm_rf", "git_push_force"]},
        {},
    ]


def test_end_session_error_does_not_convert_success_to_failed_run():
    from cron.runner import CronRunner

    store = FakeStore()
    session_db = FakeSessionDB(exc=RuntimeError("end failed"))
    runner = CronRunner(
        store,
        session_db,
        agent_factory=lambda **kwargs: FakeAgent(session_id="session-1", result="summary"),
        clock=Clock(
            datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
        ),
        id_factory=lambda: "run-1",
        approval_context_setter=lambda **kwargs: None,
    )

    run = runner.run_job(make_job(), BASE)

    assert run.status == RUN_SUCCESS
    assert run.summary == "summary"
    assert run.error is None
    assert session_db.ended_sessions == ["session-1"]
    assert store.create_run_calls == 1


def test_update_after_run_error_propagates_without_creating_failed_run():
    from cron.runner import CronRunner

    store = FakeStore()
    store.update_exc = RuntimeError("db update failed")
    runner = CronRunner(
        store,
        FakeSessionDB(),
        agent_factory=lambda **kwargs: FakeAgent(session_id="session-1", result="summary"),
        clock=Clock(
            datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
        ),
        id_factory=lambda: "run-1",
        approval_context_setter=lambda **kwargs: None,
    )

    with pytest.raises(RuntimeError, match="db update failed"):
        runner.run_job(make_job(), BASE)

    assert store.create_run_calls == 1
    assert len(store.runs) == 1
    assert store.runs[0].status == RUN_SUCCESS


def test_schedule_metadata_error_records_failed_run_without_running_agent():
    from cron.runner import CronRunner

    store = FakeStore()
    agent = FakeAgent()
    runner = CronRunner(
        store,
        FakeSessionDB(),
        agent_factory=lambda **kwargs: agent,
        clock=Clock(
            datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
        ),
        id_factory=lambda: "run-failed",
        approval_context_setter=lambda **kwargs: None,
    )
    job_next = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)

    run = runner.run_job(make_job(next_run_at=job_next, interval_seconds=None), BASE)

    assert agent.prompts == []
    assert run.status == RUN_FAILED
    assert run.session_id is None
    assert "interval_seconds is required" in run.error
    assert store.updates == [
        (
            "job-1",
            {
                "next_run_at": job_next,
                "last_run_at": datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
                "last_status": RUN_FAILED,
                "last_error": run.error,
                "now": datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
            },
        )
    ]


def test_run_job_executes_agent_loop_with_timeout_from_background_thread(tmp_path):
    from agent.loop import AgentLoop
    from config.settings import LLMConfig
    from cron.runner import CronRunner
    from db.session import SessionDB

    db = SessionDB(tmp_path / "cron-agent.db")
    store = FakeStore()
    run_results = []
    errors = []
    config = get_config()
    set_config(AppConfig(llm=LLMConfig(api_key="sk-test", request_timeout=1.0), approval=config.approval))

    def stream_events(*args, **kwargs):
        return iter([
            {"type": "content_delta", "content": "后台完成"},
            {"type": "done", "finish_reason": "stop", "content": "后台完成", "tool_calls": None},
        ])

    def run_in_background():
        try:
            runner = CronRunner(
                store,
                db,
                agent_factory=lambda **kwargs: AgentLoop(**kwargs),
                clock=Clock(
                    datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc),
                    datetime(2026, 5, 30, 10, 2, tzinfo=timezone.utc),
                ),
                id_factory=lambda: "run-1",
                approval_context_setter=lambda **kwargs: None,
            )
            with patch("llm.client.LLMClient.chat_stream", side_effect=stream_events):
                run_results.append(runner.run_job(make_job(), BASE))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_in_background)
    thread.start()
    thread.join()
    db.close()

    assert errors == []
    assert len(run_results) == 1
    assert run_results[0].status == RUN_SUCCESS
    assert run_results[0].summary == "后台完成"


def test_naive_started_at_is_rejected_before_agent_run_and_without_writing_run():
    from cron.runner import CronRunner

    store = FakeStore()
    agent = FakeAgent()
    runner = CronRunner(
        store,
        FakeSessionDB(),
        agent_factory=lambda **kwargs: agent,
        clock=Clock(datetime(2026, 5, 30, 10, 1)),
        id_factory=lambda: "run-1",
        approval_context_setter=lambda **kwargs: None,
    )

    with pytest.raises(ValueError, match="started_at must be timezone-aware"):
        runner.run_job(make_job(), BASE)

    assert agent.prompts == []
    assert store.create_run_calls == 0
    assert store.updates == []


def test_naive_scheduled_at_is_rejected():
    from cron.runner import CronRunner

    store = FakeStore()
    agent = FakeAgent()
    runner = CronRunner(
        store,
        FakeSessionDB(),
        agent_factory=lambda **kwargs: agent,
        clock=Clock(datetime(2026, 5, 30, 10, 1, tzinfo=timezone.utc)),
        id_factory=lambda: "run-1",
        approval_context_setter=lambda **kwargs: None,
    )

    with pytest.raises(ValueError, match="scheduled_at must be timezone-aware"):
        runner.run_job(make_job(schedule_type=SCHEDULE_ONCE, interval_seconds=None), datetime(2026, 5, 30, 10, 0))

    assert agent.prompts == []
    assert store.create_run_calls == 0
