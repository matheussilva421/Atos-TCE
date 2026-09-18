"""Job tracking for Mesa-owned work such as e-Contas acquisition.

The Mesa owns *which* processes are eligible and every state transition; the
external engine (today the proven PowerShell collector) only reports outcomes.
Lots and queue files stay internal details and never reach the operator.
"""

from __future__ import annotations

from collections.abc import Sequence

from .store import Store

#: Per-process acquisition lifecycle.
ACQUISITION_STATES: tuple[str, ...] = (
    "NOT_DOWNLOADED",
    "QUEUED",
    "DOWNLOADING",
    "DOWNLOADED",
    "FAILED",
)

#: Job lifecycle. ``WAITING_FOR_LOGIN`` pauses later lots instead of failing them.
JOB_STATUSES: tuple[str, ...] = (
    "PENDING",
    "RUNNING",
    "WAITING_FOR_LOGIN",
    "COMPLETED",
    "COMPLETED_WITH_ERRORS",
    "FAILED",
)

FINISHED_JOB_STATUSES: frozenset[str] = frozenset({"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"})


class JobManager:
    """Create jobs and move their items through the acquisition states."""

    def __init__(self, store: Store) -> None:
        self._store = store

    @property
    def store(self) -> Store:
        return self._store

    def create(self, job_type: str, item_ids: Sequence[int]) -> int:
        """Create a PENDING job with one QUEUED item per process id."""

        unique_ids = list(dict.fromkeys(int(value) for value in item_ids))
        job_id = self._store.create_job(job_type, total=len(unique_ids))
        for process_id in unique_ids:
            self._store.add_job_item(job_id, process_id)
        return job_id

    def start(self, job_id: int) -> None:
        self._store.set_job_status(job_id, "RUNNING", started=True)

    def mark_item(
        self, job_id: int, process_id: int, state: str, error: str | None = None
    ) -> None:
        """Record one item outcome; a failure never invalidates the others."""

        if state not in ACQUISITION_STATES:
            raise ValueError(f"unknown acquisition state: {state!r}")
        self._store.mark_job_item(job_id, process_id, state, error)

    def finish(self, job_id: int) -> None:
        job = self._store.get_job(job_id)
        if job is None:
            raise ValueError(f"unknown job: {job_id}")
        status = "COMPLETED_WITH_ERRORS" if int(job["failed"]) else "COMPLETED"
        self._store.set_job_status(job_id, status, finished=True)

    def wait_for_login(self, job_id: int, reason: str | None = None) -> None:
        """Pause the job; later lots must not run until the operator logs in."""

        self._store.set_job_status(job_id, "WAITING_FOR_LOGIN", error=reason)

    def fail(self, job_id: int, reason: str | None = None) -> None:
        self._store.set_job_status(job_id, "FAILED", finished=True, error=reason)

    def mark_downloaded(self, process_id: int) -> None:
        """Record bytes that are already available locally for a process."""

        self._store.set_process_acquisition_state(process_id, "DOWNLOADED")
