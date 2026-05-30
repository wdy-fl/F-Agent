import json
import sqlite3
from datetime import datetime, timezone

from cron.models import JOB_ACTIVE, CronJob, CronRun, ParsedSchedule


def _now() -> datetime:
    return datetime.now().astimezone()


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class CronStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_job(
        self,
        job_id: str,
        name: str,
        prompt: str,
        parsed: ParsedSchedule,
        allowed_dangerous_keys: list[str] | None = None,
        state: str = JOB_ACTIVE,
        now: datetime | None = None,
    ) -> CronJob:
        created_at = now or _now()
        keys = allowed_dangerous_keys or []
        self.conn.execute(
            """INSERT INTO cron_jobs
               (id, name, prompt, schedule_expr, schedule_type, interval_seconds, cron_expr,
                next_run_at, state, allowed_dangerous_keys, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                name,
                prompt,
                parsed.schedule_expr,
                parsed.schedule_type,
                parsed.interval_seconds,
                parsed.cron_expr,
                _to_iso(parsed.next_run_at),
                state,
                json.dumps(keys, ensure_ascii=False),
                _to_iso(created_at),
                _to_iso(created_at),
            ),
        )
        self.conn.commit()
        job = self.get_job(job_id)
        if job is None:
            raise RuntimeError(f"failed to create cron job: {job_id}")
        return job

    def get_job(self, job_id: str) -> CronJob | None:
        cur = self.conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        return self._job_from_row(row) if row else None

    def list_jobs(self) -> list[CronJob]:
        cur = self.conn.execute("SELECT * FROM cron_jobs ORDER BY created_at ASC")
        return [self._job_from_row(row) for row in cur.fetchall()]

    def list_due_jobs(self, now: datetime) -> list[CronJob]:
        cur = self.conn.execute(
            """SELECT * FROM cron_jobs
               WHERE state = ? AND next_run_at IS NOT NULL AND next_run_at <= ?
               ORDER BY next_run_at ASC""",
            (JOB_ACTIVE, _to_iso(now)),
        )
        return [self._job_from_row(row) for row in cur.fetchall()]

    def update_job_state(self, job_id: str, state: str, now: datetime | None = None) -> None:
        updated_at = now or _now()
        self.conn.execute(
            "UPDATE cron_jobs SET state = ?, updated_at = ? WHERE id = ?",
            (state, _to_iso(updated_at), job_id),
        )
        self.conn.commit()

    def delete_job(self, job_id: str) -> None:
        self.conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        self.conn.commit()

    def update_after_run(
        self,
        job_id: str,
        *,
        next_run_at: datetime | None,
        last_run_at: datetime,
        last_status: str,
        last_error: str | None = None,
        state: str | None = None,
        now: datetime | None = None,
    ) -> None:
        updated_at = now or _now()
        if state is None:
            self.conn.execute(
                """UPDATE cron_jobs
                   SET next_run_at = ?, last_run_at = ?, last_status = ?, last_error = ?, updated_at = ?
                   WHERE id = ?""",
                (_to_iso(next_run_at), _to_iso(last_run_at), last_status, last_error, _to_iso(updated_at), job_id),
            )
        else:
            self.conn.execute(
                """UPDATE cron_jobs
                   SET next_run_at = ?, last_run_at = ?, last_status = ?, last_error = ?, state = ?, updated_at = ?
                   WHERE id = ?""",
                (_to_iso(next_run_at), _to_iso(last_run_at), last_status, last_error, state, _to_iso(updated_at), job_id),
            )
        self.conn.commit()

    def create_run(
        self,
        run_id: str,
        job_id: str,
        scheduled_at: datetime,
        status: str,
        session_id: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        summary: str | None = None,
        error: str | None = None,
    ) -> CronRun:
        self.conn.execute(
            """INSERT INTO cron_runs
               (id, job_id, session_id, scheduled_at, started_at, finished_at, status, summary, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                job_id,
                session_id,
                _to_iso(scheduled_at),
                _to_iso(started_at),
                _to_iso(finished_at),
                status,
                summary,
                error,
            ),
        )
        self.conn.commit()
        run = self.get_run(run_id)
        if run is None:
            raise RuntimeError(f"failed to create cron run: {run_id}")
        return run

    def get_run(self, run_id: str) -> CronRun | None:
        cur = self.conn.execute("SELECT * FROM cron_runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        return self._run_from_row(row) if row else None

    def list_runs(self, job_id: str) -> list[CronRun]:
        cur = self.conn.execute(
            "SELECT * FROM cron_runs WHERE job_id = ? ORDER BY scheduled_at ASC",
            (job_id,),
        )
        return [self._run_from_row(row) for row in cur.fetchall()]

    def _job_from_row(self, row: sqlite3.Row) -> CronJob:
        return CronJob(
            id=row["id"],
            name=row["name"],
            prompt=row["prompt"],
            schedule_expr=row["schedule_expr"],
            schedule_type=row["schedule_type"],
            interval_seconds=row["interval_seconds"],
            cron_expr=row["cron_expr"],
            next_run_at=_from_iso(row["next_run_at"]),
            state=row["state"],
            allowed_dangerous_keys=json.loads(row["allowed_dangerous_keys"] or "[]"),
            created_at=_from_iso(row["created_at"]),
            updated_at=_from_iso(row["updated_at"]),
            last_run_at=_from_iso(row["last_run_at"]),
            last_status=row["last_status"],
            last_error=row["last_error"],
        )

    def _run_from_row(self, row: sqlite3.Row) -> CronRun:
        return CronRun(
            id=row["id"],
            job_id=row["job_id"],
            session_id=row["session_id"],
            scheduled_at=_from_iso(row["scheduled_at"]),
            started_at=_from_iso(row["started_at"]),
            finished_at=_from_iso(row["finished_at"]),
            status=row["status"],
            summary=row["summary"],
            error=row["error"],
        )
