"""Cron 后台调度器。"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from config.settings import CronConfig
from cron.models import JOB_MISSED
from cron.runner import CronRunner
from cron.store import CronStore


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now().astimezone()


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _require_timezone_aware(value: datetime, name: str) -> datetime:
    if not _is_timezone_aware(value):
        raise ValueError(f"{name} must be timezone-aware")
    return value


class CronScheduler:
    """按固定间隔扫描并串行执行到期 Cron 任务。"""

    def __init__(
        self,
        store: CronStore,
        runner: CronRunner,
        config: CronConfig,
        clock: Callable[[], datetime] | None = None,
        thread_factory: Callable[..., threading.Thread] | None = None,
    ):
        self.store = store
        self.runner = runner
        self.config = config
        self.clock = clock or _now
        self.thread_factory = thread_factory or threading.Thread
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self, now: datetime | None = None) -> None:
        if not self.config.enabled:
            return

        current = _require_timezone_aware(now or self.clock(), "now")
        grace = timedelta(seconds=self.config.grace_seconds)

        for job in self.store.list_due_jobs(current):
            scheduled_at = job.next_run_at
            if scheduled_at is None:
                continue

            try:
                _require_timezone_aware(scheduled_at, "scheduled_at")
                is_past_grace = current - scheduled_at > grace
            except (TypeError, ValueError):
                logger.exception("Skipping cron job %s with invalid scheduled_at", job.id)
                continue

            if is_past_grace:
                self.store.update_job_state(job.id, JOB_MISSED, now=current)
                continue

            try:
                self.runner.run_job(job, scheduled_at=scheduled_at)
            except Exception:
                logger.exception("Cron job %s runner failed", job.id)
                continue

    def start(self) -> None:
        if not self.config.enabled:
            return
        if self._thread is not None:
            if self._thread.is_alive():
                return
            self._thread = None

        self._stop_event.clear()
        self._thread = self.thread_factory(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if not self._thread.is_alive():
                self._thread = None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Cron scheduler tick failed")
            self._stop_event.wait(self.config.tick_interval_seconds)
