import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from cron.models import JOB_ACTIVE, JOB_PAUSED, CronJob
from tools.registry import registry as global_registry


class FakeCronStore:
    def __init__(self):
        self.created = []
        self.jobs = []
        self.state_updates = []
        self.deleted = []

    def create_job(self, **kwargs):
        self.created.append(kwargs)
        parsed = kwargs["parsed"]
        now = kwargs["now"]
        job = CronJob(
            id=kwargs["job_id"],
            name=kwargs["name"],
            prompt=kwargs["prompt"],
            schedule_expr=parsed.schedule_expr,
            schedule_type=parsed.schedule_type,
            interval_seconds=parsed.interval_seconds,
            cron_expr=parsed.cron_expr,
            next_run_at=parsed.next_run_at,
            state=JOB_ACTIVE,
            allowed_dangerous_keys=kwargs.get("allowed_dangerous_keys") or [],
            created_at=now,
            updated_at=now,
        )
        self.jobs.append(job)
        return job

    def list_jobs(self):
        return list(self.jobs)

    def update_job_state(self, job_id, state, now=None):
        self.state_updates.append({"job_id": job_id, "state": state, "now": now})

    def delete_job(self, job_id):
        self.deleted.append(job_id)


def _load_cron_tool():
    import tools.cron

    return importlib.reload(tools.cron)


def _decode(result):
    return json.loads(result)


@pytest.fixture(autouse=True)
def reset_cron_tool_state():
    cron_tool = _load_cron_tool()
    cron_tool.set_cron_store(None)
    cron_tool.set_cron_confirm_callback(None)
    yield
    cron_tool.set_cron_store(None)
    cron_tool.set_cron_confirm_callback(None)


def test_cron_tool_registered_after_tools_import():
    global_registry.deregister("cron")

    import tools
    import tools.cron

    importlib.reload(tools.cron)
    importlib.reload(tools)

    assert global_registry.has_tool("cron")


def test_create_without_confirmation_callback_does_not_create_job():
    cron_tool = _load_cron_tool()
    store = FakeCronStore()
    cron_tool.set_cron_store(store)
    cron_tool.set_cron_confirm_callback(None)

    result = _decode(cron_tool.run_cron_tool({
        "action": "create",
        "name": "daily summary",
        "prompt": "summarize",
        "schedule": "10m",
    }))

    assert result == {"ok": False, "error": "cron confirmation callback is not configured"}
    assert store.created == []


def test_create_cancelled_by_confirmation_callback_does_not_create_job():
    cron_tool = _load_cron_tool()
    store = FakeCronStore()
    payloads = []
    cron_tool.set_cron_store(store)
    cron_tool.set_cron_confirm_callback(lambda payload: payloads.append(payload) or False)

    result = _decode(cron_tool.run_cron_tool({
        "action": "create",
        "name": "daily summary",
        "prompt": "summarize",
        "schedule": "every 1h",
    }))

    assert result == {"ok": False, "cancelled": True}
    assert store.created == []
    assert payloads[0]["action"] == "create"
    assert payloads[0]["name"] == "daily summary"


def test_create_confirmed_parses_schedule_creates_job_and_returns_serialized_job():
    cron_tool = _load_cron_tool()
    store = FakeCronStore()
    payloads = []
    cron_tool.set_cron_store(store)
    cron_tool.set_cron_confirm_callback(lambda payload: payloads.append(payload) or True)

    result = _decode(cron_tool.run_cron_tool({
        "action": "create",
        "name": "standup",
        "prompt": "prepare standup",
        "schedule": "10m",
        "allowed_dangerous_keys": ["terminal:git status"],
    }))

    assert result["ok"] is True
    assert result["job"]["id"]
    assert result["job"]["name"] == "standup"
    assert result["job"]["prompt"] == "prepare standup"
    assert result["job"]["schedule_expr"] == "10m"
    assert result["job"]["schedule_type"] == "once"
    assert result["job"]["allowed_dangerous_keys"] == ["terminal:git status"]
    assert isinstance(result["job"]["next_run_at"], str)
    assert isinstance(result["job"]["created_at"], str)
    assert store.created[0]["name"] == "standup"
    assert store.created[0]["prompt"] == "prepare standup"
    assert store.created[0]["parsed"].schedule_expr == "10m"
    assert store.created[0]["allowed_dangerous_keys"] == ["terminal:git status"]
    assert store.created[0]["now"].tzinfo is not None
    assert payloads == [{
        "action": "create",
        "name": "standup",
        "prompt": "prepare standup",
        "schedule": "10m",
        "schedule_type": "once",
        "next_run_at": store.created[0]["parsed"].next_run_at.isoformat(),
        "allowed_dangerous_keys": ["terminal:git status"],
    }]


def test_set_cron_store_closes_internal_session_db(monkeypatch):
    cron_tool = _load_cron_tool()
    closed = []

    class FakeSessionDB:
        conn = object()

        def __init__(self, db_path):
            self.db_path = db_path

        def close(self):
            closed.append(self.db_path)

    class FakeCronStore:
        def __init__(self, conn):
            self.conn = conn

        def list_jobs(self):
            return []

    class FakeConfig:
        db_path = "cron-test.db"

    monkeypatch.setattr(cron_tool, "SessionDB", FakeSessionDB)
    monkeypatch.setattr(cron_tool, "CronStore", FakeCronStore)
    monkeypatch.setattr(cron_tool, "get_config", lambda: FakeConfig())

    result = _decode(cron_tool.run_cron_tool({"action": "list"}))
    cron_tool.set_cron_store(None)

    assert result == {"ok": True, "jobs": []}
    assert closed == ["cron-test.db"]


def test_list_returns_jobs_with_serialized_datetimes():
    cron_tool = _load_cron_tool()
    store = FakeCronStore()
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    job = CronJob(
        id="job-1",
        name="job",
        prompt="prompt",
        schedule_expr="every 1h",
        schedule_type="interval",
        interval_seconds=3600,
        cron_expr=None,
        next_run_at=now + timedelta(hours=1),
        state=JOB_ACTIVE,
        allowed_dangerous_keys=[],
        created_at=now,
        updated_at=now,
    )
    store.jobs.append(job)
    cron_tool.set_cron_store(store)

    result = _decode(cron_tool.run_cron_tool({"action": "list"}))

    assert result == {
        "ok": True,
        "jobs": [{
            "id": "job-1",
            "name": "job",
            "prompt": "prompt",
            "schedule_expr": "every 1h",
            "schedule_type": "interval",
            "interval_seconds": 3600,
            "cron_expr": None,
            "next_run_at": "2026-05-30T13:00:00+00:00",
            "state": JOB_ACTIVE,
            "allowed_dangerous_keys": [],
            "created_at": "2026-05-30T12:00:00+00:00",
            "updated_at": "2026-05-30T12:00:00+00:00",
            "last_run_at": None,
            "last_status": None,
            "last_error": None,
        }],
    }


def test_pause_resume_remove_call_store_methods():
    cron_tool = _load_cron_tool()
    store = FakeCronStore()
    cron_tool.set_cron_store(store)

    pause = _decode(cron_tool.run_cron_tool({"action": "pause", "job_id": "job-1"}))
    resume = _decode(cron_tool.run_cron_tool({"action": "resume", "job_id": "job-1"}))
    remove = _decode(cron_tool.run_cron_tool({"action": "remove", "job_id": "job-1"}))

    assert pause == {"ok": True, "job_id": "job-1", "state": JOB_PAUSED}
    assert resume == {"ok": True, "job_id": "job-1", "state": JOB_ACTIVE}
    assert remove == {"ok": True, "job_id": "job-1", "removed": True}
    assert store.state_updates[0]["job_id"] == "job-1"
    assert store.state_updates[0]["state"] == JOB_PAUSED
    assert store.state_updates[0]["now"].tzinfo is not None
    assert store.state_updates[1]["job_id"] == "job-1"
    assert store.state_updates[1]["state"] == JOB_ACTIVE
    assert store.state_updates[1]["now"].tzinfo is not None
    assert store.deleted == ["job-1"]


def test_invalid_inputs_return_errors_without_raising():
    cron_tool = _load_cron_tool()
    store = FakeCronStore()
    cron_tool.set_cron_store(store)
    cron_tool.set_cron_confirm_callback(lambda payload: payload is not None)

    unknown = _decode(cron_tool.run_cron_tool({"action": "run_now"}))
    invalid_schedule = _decode(cron_tool.run_cron_tool({
        "action": "create",
        "name": "bad schedule",
        "prompt": "prompt",
        "schedule": "tomorrow morning",
    }))
    missing_action = _decode(cron_tool.run_cron_tool({}))
    missing_create_arg = _decode(cron_tool.run_cron_tool({"action": "create", "name": "missing"}))
    missing_job_id = _decode(cron_tool.run_cron_tool({"action": "pause"}))

    assert unknown["ok"] is False
    assert "unknown action" in unknown["error"]
    assert invalid_schedule["ok"] is False
    assert "Unsupported schedule" in invalid_schedule["error"]
    assert missing_action["ok"] is False
    assert "action is required" in missing_action["error"]
    assert missing_create_arg["ok"] is False
    assert "prompt is required" in missing_create_arg["error"]
    assert missing_job_id["ok"] is False
    assert "job_id is required" in missing_job_id["error"]
    assert store.created == []
