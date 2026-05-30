"""Cron 任务独立会话执行器。"""

import uuid
from collections.abc import Callable
from datetime import datetime

from agent.loop import AgentLoop
from config.settings import get_config
from cron.models import RUN_FAILED, RUN_SUCCESS, CronJob, CronRun
from cron.parser import compute_following_run
from cron.store import CronStore
from db.session import SessionDB
from tools.approval import set_approval_callback, set_approval_context
from tools.cron import set_cron_confirm_callback, set_cron_store


def _now() -> datetime:
    return datetime.now().astimezone()


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _require_timezone_aware(value: datetime, name: str) -> datetime:
    if not _is_timezone_aware(value):
        raise ValueError(f"{name} must be timezone-aware")
    return value


class CronRunner:
    """在独立 Agent 会话中执行单个 CronJob。"""

    def __init__(
        self,
        store: CronStore,
        session_db: SessionDB,
        agent_factory: Callable[..., AgentLoop] | None = None,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
        approval_context_setter: Callable[..., None] | None = None,
    ):
        self.store = store
        self.session_db = session_db
        self.agent_factory = agent_factory or self._create_agent
        self.clock = clock or _now
        self.id_factory = id_factory or (lambda: str(uuid.uuid4()))
        self.approval_context_setter = approval_context_setter or set_approval_context

    def run_job(self, job: CronJob, scheduled_at: datetime) -> CronRun:
        scheduled_at = _require_timezone_aware(scheduled_at, "scheduled_at")
        started_at = _require_timezone_aware(self.clock(), "started_at")
        run_id = self.id_factory()

        try:
            try:
                next_run_at = compute_following_run(
                    job.schedule_type,
                    scheduled_at,
                    interval_seconds=job.interval_seconds,
                    cron_expr=job.cron_expr,
                )
            except Exception as exc:
                finished_at = _require_timezone_aware(self.clock(), "finished_at")
                error = str(exc)
                run = self.store.create_run(
                    run_id,
                    job.id,
                    scheduled_at,
                    RUN_FAILED,
                    session_id=None,
                    started_at=started_at,
                    finished_at=finished_at,
                    error=error,
                )
                self.store.update_after_run(
                    job.id,
                    next_run_at=job.next_run_at,
                    last_run_at=finished_at,
                    last_status=RUN_FAILED,
                    last_error=error,
                    now=finished_at,
                )
                return run

            set_approval_callback(None)
            set_cron_confirm_callback(None)
            set_cron_store(self.store)
            agent = self.agent_factory(session_db=self.session_db, output_callback=lambda text: len(text))
            mode = get_config().approval.mode

            try:
                self.approval_context_setter(
                    mode=mode,
                    session_id=None,
                    allowed_dangerous_keys=job.allowed_dangerous_keys,
                )
                result = agent.run(job.prompt)
            except Exception as exc:
                session_id = getattr(agent, "session_id", None)
                if session_id:
                    try:
                        self.session_db.end_session(session_id)
                    except Exception:
                        pass
                finished_at = _require_timezone_aware(self.clock(), "finished_at")
                error = str(exc)
                run = self.store.create_run(
                    run_id,
                    job.id,
                    scheduled_at,
                    RUN_FAILED,
                    session_id=session_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    error=error,
                )
                self.store.update_after_run(
                    job.id,
                    next_run_at=job.next_run_at,
                    last_run_at=finished_at,
                    last_status=RUN_FAILED,
                    last_error=error,
                    now=finished_at,
                )
                return run

            session_id = agent.session_id
            if session_id:
                self.approval_context_setter(
                    mode=mode,
                    session_id=session_id,
                    allowed_dangerous_keys=job.allowed_dangerous_keys,
                )
                try:
                    self.session_db.end_session(session_id)
                except Exception:
                    pass
            finished_at = _require_timezone_aware(self.clock(), "finished_at")
            run = self.store.create_run(
                run_id,
                job.id,
                scheduled_at,
                RUN_SUCCESS,
                session_id=session_id,
                started_at=started_at,
                finished_at=finished_at,
                summary=result,
            )
            self.store.update_after_run(
                job.id,
                next_run_at=next_run_at,
                last_run_at=finished_at,
                last_status=RUN_SUCCESS,
                last_error=None,
                now=finished_at,
            )
            return run
        finally:
            self.approval_context_setter()

    def _create_agent(self, **kwargs) -> AgentLoop:
        return AgentLoop(**kwargs)
