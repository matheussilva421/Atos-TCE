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
    "INTERRUPTED",
    "COMPLETED",
    "COMPLETED_WITH_ERRORS",
    "FAILED",
)

#: Statuses a job may be resumed from: a login pause and an interrupted run are
#: both "the work stopped halfway", never "the work failed".
RESUMABLE_JOB_STATUSES: frozenset[str] = frozenset({"WAITING_FOR_LOGIN", "INTERRUPTED"})

FINISHED_JOB_STATUSES: frozenset[str] = frozenset({"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"})

#: Per-process analysis lifecycle.
ANALYSIS_STATES: tuple[str, ...] = ("QUEUED", "ANALISANDO", "ANALISADO", "FAILED")


class JobManager:
    """Create jobs and move their items through the acquisition states."""

    def __init__(
        self,
        store: Store,
        *,
        states: tuple[str, ...] = ACQUISITION_STATES,
        done_state: str = "DOWNLOADED",
    ) -> None:
        self._store = store
        self._states = states
        self._done_state = done_state

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

        if state not in self._states:
            raise ValueError(f"unknown acquisition state: {state!r}")
        self._store.mark_job_item(
            job_id, process_id, state, error, done_state=self._done_state
        )

    def finish(self, job_id: int) -> None:
        job = self._store.get_job(job_id)
        if job is None:
            raise ValueError(f"unknown job: {job_id}")
        status = "COMPLETED_WITH_ERRORS" if int(job["failed"]) else "COMPLETED"
        self._store.set_job_status(job_id, status, finished=True, done_state=self._done_state)

    def wait_for_login(self, job_id: int, reason: str | None = None) -> None:
        """Pause the job; later lots must not run until the operator logs in."""

        self._store.set_job_status(job_id, "WAITING_FOR_LOGIN", error=reason)

    def fail(self, job_id: int, reason: str | None = None) -> None:
        self._store.set_job_status(job_id, "FAILED", finished=True, error=reason)

    def mark_downloaded(self, process_id: int) -> None:
        """Record bytes that are already available locally for a process."""

        self._store.set_process_acquisition_state(process_id, "DOWNLOADED")
