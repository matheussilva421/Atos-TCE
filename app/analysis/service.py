"""Analysis service: runs the proven engine and stores what the Mesa shows.

One worker thread owns the typed queue, so acquisition and analysis never fight
over a second process-wide executor. Each successful download enqueues exactly
one analysis job, and a failure is item-local: the process becomes ERRO while
the downloaded bytes and the rest of the job survive.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ..core.jobs import ANALYSIS_STATES, JobManager
from ..core.store import Store
from .legacy_adapter import AnalysisError, LegacyAnalysisAdapter
from .normalize import NormalizedAnalysis, normalize_analysis


class AnalysisService:
    def __init__(
        self,
        store: Store,
        data_root: str | Path,
        *,
        adapter: Any | None = None,
        repo_root: str | Path | None = None,
        normalizer: Callable[..., NormalizedAnalysis] = normalize_analysis,
    ) -> None:
        self._store = store
        self._data_root = Path(data_root)
        self._adapter = adapter or LegacyAnalysisAdapter(data_root, repo_root=repo_root)
        self._normalizer = normalizer
        self._jobs = JobManager(store, states=ANALYSIS_STATES, done_state="ANALISADO")
        self._queue: queue.Queue[int] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ queue

    def backfill_candidates(self) -> list[int]:
        """Return local process rows that can be analysed without downloading."""

        candidates: list[int] = []
        eligible = {"PENDENTE", "BAIXADO", "REVISAR", "ERRO", "CONCLUÍDO", "PREENCHIDO"}
        for process in self._store.list_processes():
            if str(process.get("status") or "") not in eligible:
                continue
            if str(process.get("acquisition_state") or "") != "DOWNLOADED":
                continue
            if not self._store.list_documents(int(process["id"])):
                continue
            candidates.append(int(process["id"]))
        return candidates

    def enqueue_backfill(self) -> tuple[int, int]:
        """Queue one resumable analysis job for every eligible local process."""

        if self._store.count_active_jobs("analysis"):
            raise AnalysisError("já existe uma análise em andamento")
        process_ids = self.backfill_candidates()
        if not process_ids:
            raise AnalysisError("nenhum processo com PDF local aguarda análise")
        job_id = self._jobs.create("analysis", process_ids)
        self._ensure_worker()
        self._queue.put(job_id)
        return job_id, len(process_ids)

    def enqueue(self, process_id: int) -> int:
        """Create one analysis job for a process and hand it to the worker."""

        job_id = self._jobs.create("analysis", [int(process_id)])
        self._ensure_worker()
        self._queue.put(job_id)
        return job_id

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._consume, name="analysis-worker", daemon=True
                )
                self._worker.start()

    def _consume(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self.run(job_id)
            except Exception:  # a broken job must never kill the worker
                try:
                    self._jobs.fail(job_id, "falha inesperada do serviço de análise")
                except Exception:  # pragma: no cover - best effort
                    pass
            finally:
                self._queue.task_done()

    def drain(self) -> bool:
        """Wait for the queue to empty; used by tests and by shutdown paths."""

        self._queue.join()
        return True

    # ------------------------------------------------------------------- work

    def run(self, job_id: int) -> None:
        """Analyze every item of one job, in order, without stopping on error."""

        if self._store.get_job(job_id) is None:
            raise AnalysisError(f"unknown job: {job_id}")
        self._jobs.start(job_id)
        for item in self._store.list_job_items(job_id):
            process_id = int(item["process_id"])
            self._jobs.mark_item(job_id, process_id, "ANALISANDO")
            try:
                self.analyze_one(process_id)
            except Exception as error:
                self._jobs.mark_item(job_id, process_id, "FAILED", _safe_message(error))
                continue
            self._jobs.mark_item(job_id, process_id, "ANALISADO")
        self._jobs.finish(job_id)

    def analyze_one(self, process_id: int) -> str:
        """Analyze one process and return the resulting workflow status."""

        process = self._store.get_process(process_id)
        if process is None:
            raise AnalysisError(f"unknown process: {process_id}")
        process_key = str(process["process_key"])
        original_status = str(process.get("status") or "")
        preserve_terminal = original_status in {"CONCLUÍDO", "PREENCHIDO"}
        if preserve_terminal:
            self._store.add_workflow_event(process_id, "analysis_started")
        else:
            self._store.set_process_status(process_id, "ANALISANDO", event_type="analysis_started")
        try:
            documents = self._store.list_documents(process_id)
            payload = self._adapter.analyze(process_key, process=process, documents=documents)
            analysis = self._normalizer(
                process_key,
                payload,
                documents=documents,
                interested=str(process.get("interested_normalized") or process.get("interested") or ""),
            )
        except Exception as error:
            payload = {"error": _safe_message(error)}
            if preserve_terminal:
                self._store.add_workflow_event(process_id, "analysis_failed", payload)
            else:
                self._store.set_process_status(
                    process_id,
                    "ERRO",
                    event_type="analysis_failed",
                    payload=payload,
                )
            raise

        self._store.replace_fields(process_id, analysis.fields)
        final_status = original_status if preserve_terminal else analysis.process_status
        payload = {
            "status": final_status,
            "analysis_status": analysis.process_status,
            "pending": analysis.pending_fields,
            "legacy_status": analysis.legacy_status,
            "field_count": len(analysis.fields),
        }
        if preserve_terminal:
            self._store.add_workflow_event(process_id, "analysis_finished", payload)
        else:
            self._store.set_process_status(
                process_id,
                final_status,
                event_type="analysis_finished",
                payload=payload,
            )
        return final_status


def _safe_message(error: BaseException, limit: int = 300) -> str:
    text = f"{type(error).__name__}: {error}"
    return text[:limit]
