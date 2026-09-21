"""Acquisition coordinator: the Mesa decides, the proven collector downloads.

The operator sees one action ("baixar processos pendentes"). Internally the
service batches the selection, writes one frozen queue for the whole plan and
runs the lots serially, canonicalizing the archive after each lot so newly
downloaded bytes become SHA-256 blobs with a hardlinked process view.

Failures are item-local: a failed lot or process never erases the successes of
previous lots, and an authentication problem pauses the job instead of
continuing blindly.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..archive.legacy_import import (
    canonicalize_process_tree,
    collect_process_documents,
)
from ..core.jobs import RESUMABLE_JOB_STATUSES, JobManager
from ..core.store import Store
from .collector import CollectorRequest, CollectorResult, redact, run_collector
from .legacy_queue import DEFAULT_LOT_SIZE, SOURCE_SCOPES, write_frozen_queue

QUEUE_TREE = "queues"
ARCHIVE_TREE = "archive"


class AcquisitionError(RuntimeError):
    """Raised when an acquisition cannot be planned or started."""


@dataclass(slots=True)
class AcquisitionPlan:
    process_ids: list[int]
    process_keys: list[str]
    lot_size: int = DEFAULT_LOT_SIZE

    @property
    def total(self) -> int:
        return len(self.process_ids)

    @property
    def lot_count(self) -> int:
        if self.total == 0:
            return 0
        size = max(1, self.lot_size)
        return -(-self.total // size)

    def lot_ids(self, lot_number: int) -> list[int]:
        """One-based lot slice, mirroring how the frozen queue is written."""

        size = max(1, self.lot_size)
        start = (max(1, lot_number) - 1) * size
        return self.process_ids[start : start + size]


class AcquisitionService:
    def __init__(
        self,
        store: Store,
        data_root: str | Path,
        *,
        lot_size: int = DEFAULT_LOT_SIZE,
        repo_root: str | Path | None = None,
        runner: Callable[..., object] | None = None,
        jobs: JobManager | None = None,
        keep_browser_open: bool = True,
        analysis: Any | None = None,
    ) -> None:
        self._store = store
        self._data_root = Path(data_root)
        self._lot_size = max(1, int(lot_size))
        self._repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
        self._runner = runner
        self._jobs = jobs or JobManager(store)
        self._keep_browser_open = keep_browser_open
        #: M4: a successful download schedules exactly one analysis job.
        self._analysis = analysis
        self._lock = threading.Lock()

    # ------------------------------------------------------------------- plan

    def plan_pending(self) -> AcquisitionPlan:
        rows = self._store.list_missing_pending_processes()
        return AcquisitionPlan(
            process_ids=[int(row["id"]) for row in rows],
            process_keys=[str(row["process_key"]) for row in rows],
            lot_size=self._lot_size,
        )

    def queue_path(self, job_id: int) -> Path:
        return self._data_root / QUEUE_TREE / f"acquisition-{int(job_id)}.json"

    def receipt_path(self, job_id: int, lot_number: int) -> Path:
        """Where the collector writes the per-process receipt of one lot."""

        return self._data_root / "logs" / f"collector-{int(job_id)}-lot-{int(lot_number)}.json"

    def _scan_spec(self) -> tuple[str, dict[str, object]]:
        scan = self._store.latest_area_scan()
        if scan is None:
            return "sector_finalistic", {}
        scope = str(scan.get("source_scope") or "sector_finalistic")
        if scope not in SOURCE_SCOPES:
            scope = "sector_finalistic"
        marker: dict[str, object] = {}
        if scan.get("marker_label") or scan.get("marker_value"):
            marker = {"label": scan.get("marker_label"), "value": scan.get("marker_value")}
        return scope, marker

    # ---------------------------------------------------------------- lifecycle

    def start(self, plan: AcquisitionPlan) -> int:
        """Create the job and its frozen queue; refuse a second active job."""

        if plan.total == 0:
            raise AcquisitionError("não há processos pendentes para baixar")
        with self._lock:
            if self._store.count_active_jobs("acquisition"):
                raise AcquisitionError("já existe uma aquisição em andamento")
            job_id = self._jobs.create("acquisition", plan.process_ids)
            scope, marker = self._scan_spec()
            write_frozen_queue(
                [{"process_key": key} for key in plan.process_keys],
                scope,
                marker,
                self.queue_path(job_id),
                self._lot_size,
            )
        return job_id

    def start_async(self, plan: AcquisitionPlan) -> int:
        job_id = self.start(plan)
        thread = threading.Thread(
            target=self._run_guarded, args=(job_id,), name=f"acquisition-{job_id}", daemon=True
        )
        thread.start()
        return job_id

    def resume_async(self, job_id: int) -> int:
        """Continue a job that paused for login or was interrupted by a restart.

        The queue is rebuilt from the job itself, every item that already
        reached DOWNLOADED is kept, and only the incomplete ones run again. The
        status transition happens inside the lock, so two resumes can never run
        the same job twice.
        """

        with self._lock:
            job = self._store.get_job(job_id)
            if job is None:
                raise AcquisitionError(f"unknown job: {job_id}")
            status = str(job["status"])
            if status not in RESUMABLE_JOB_STATUSES:
                raise AcquisitionError(
                    "só um job pausado por login ou interrompido pode ser retomado"
                )
            self._store.set_job_status(job_id, "PENDING", clear_error=True)
        thread = threading.Thread(
            target=self._run_guarded, args=(job_id,), name=f"acquisition-{job_id}", daemon=True
        )
        thread.start()
        return job_id

    def _run_guarded(self, job_id: int) -> None:
        try:
            self.run(job_id)
        except Exception as error:  # the worker must never die silently
            try:
                self._jobs.fail(job_id, redact(str(error))[:300])
            except Exception:  # pragma: no cover - best effort
                pass

    def run(self, job_id: int) -> None:
        """Run every internal lot serially, updating state after each one."""

        job = self._store.get_job(job_id)
        if job is None:
            raise AcquisitionError(f"unknown job: {job_id}")
        plan = self._plan_from_job(job_id)
        if plan.total == 0:
            self._jobs.finish(job_id)
            return

        scope, marker = self._scan_spec()
        queue_path = self.queue_path(job_id)
        info = write_frozen_queue(
            [{"process_key": key} for key in plan.process_keys],
            scope,
            marker,
            queue_path,
            self._lot_size,
        )
        # A resumed job never repeats what already reached DOWNLOADED.
        done = {
            int(item["process_id"])
            for item in self._store.list_job_items(job_id)
            if str(item["state"]) == "DOWNLOADED"
        }
        self._jobs.start(job_id)
        paused = False
        for lot_number in range(1, info.lot_count + 1):
            lot_ids = [process_id for process_id in plan.lot_ids(lot_number) if process_id not in done]
            if not lot_ids:
                continue
            for process_id in lot_ids:
                self._jobs.mark_item(job_id, process_id, "DOWNLOADING")
            result = run_collector(
                CollectorRequest(
                    queue_path=queue_path,
                    lot_number=lot_number,
                    destination=self._data_root / ARCHIVE_TREE,
                    source_scope=scope,
                    keep_browser_open=self._keep_browser_open,
                    receipt_path=self.receipt_path(job_id, lot_number),
                ),
                repo_root=self._repo_root,
                runner=self._runner,
            )
            canonicalize_process_tree(self._data_root, self._store)
            if result.auth_required:
                # Authentication is a pause, not an item failure. The
                # collector may have stopped before producing a trustworthy
                # receipt, so keep the whole interrupted lot queued for the
                # operator's explicit resume.
                for process_id in lot_ids:
                    self._jobs.mark_item(job_id, process_id, "QUEUED")
                self._jobs.wait_for_login(job_id, "o e-Contas pediu login")
                paused = True
                break
            keys_by_id = dict(zip(plan.process_ids, plan.process_keys, strict=False))
            self._register_lot(
                job_id, lot_ids, [keys_by_id[process_id] for process_id in lot_ids], result
            )
        if not paused:
            self._jobs.finish(job_id)

    # ----------------------------------------------------------------- helpers

    def _plan_from_job(self, job_id: int) -> AcquisitionPlan:
        processes = {int(row["id"]): row for row in self._store.list_processes()}
        ordered = [
            int(item["process_id"])
            for item in self._store.list_job_items(job_id)
            if int(item["process_id"]) in processes
        ]
        return AcquisitionPlan(
            process_ids=ordered,
            process_keys=[str(processes[process_id]["process_key"]) for process_id in ordered],
            lot_size=self._lot_size,
        )

    def _register_lot(
        self,
        job_id: int,
        lot_ids: list[int],
        lot_keys: list[str],
        result: CollectorResult,
    ) -> None:
        """Decide per process from the collector's receipt, never from files alone.

        A process only becomes DOWNLOADED when the collector says the lot
        finished for it *and* the documents really are in the acervo. Files
        left behind by an earlier partial run can no longer become a success,
        and a receipt that names a process outside the lot fails the lot.
        """

        keys_by_id = dict(zip(lot_ids, lot_keys, strict=False))
        outside = sorted(set(result.per_process) - set(lot_keys))
        if outside:
            reason = "recibo do coletor trouxe processo fora do lote: " + ", ".join(outside[:5])
            for process_id in lot_ids:
                self._jobs.mark_item(job_id, process_id, "FAILED", reason)
            return
        for process_id in lot_ids:
            key = keys_by_id[process_id]
            outcome = result.per_process.get(key)
            if outcome is None:
                # No receipt is not a success: the file may be a leftover from
                # an earlier partial run. The collector's own error is kept so
                # the operator sees why the lot stopped.
                reason = "o coletor não devolveu resultado para este processo"
                if result.error:
                    reason = f"{reason}: {redact(result.error)[:200]}"
                elif result.auth_required:
                    reason = "login necessário no e-Contas"
                self._jobs.mark_item(
                    job_id,
                    process_id,
                    "FAILED",
                    reason,
                )
                continue
            state = str(outcome.get("outcome") or "").strip().lower()
            if state == "auth_required":
                self._jobs.mark_item(job_id, process_id, "FAILED", "login necessário no e-Contas")
                continue
            if state != "completed":
                reason = redact(str(outcome.get("error") or ""))[:300] or (
                    f"o coletor recusou o processo ({state or 'sem resultado'})"
                )
                self._jobs.mark_item(job_id, process_id, "FAILED", reason)
                continue
            documents = collect_process_documents(self._data_root, key)
            if not documents:
                self._jobs.mark_item(
                    job_id,
                    process_id,
                    "FAILED",
                    "o coletor declarou sucesso, mas nenhum documento apareceu no acervo",
                )
                continue
            self._store.replace_documents(process_id, documents)
            self._jobs.mark_item(job_id, process_id, "DOWNLOADED")
            if self._analysis is not None:
                self._analysis.enqueue(process_id)
