#!/usr/bin/env python
"""Prove that one bounded e-Contas acquisition downloaded only the requested keys.

The M3 real gate asks a single question: did the job touch exactly the keys the
Mesa asked for? This tool answers it from local state only — the frozen queue the
job used, the job's items and the processes the store saw — and it never talks to
the portal. Violations (exit 1) are: a key downloaded without being requested, a
requested key the job never attempted, an item still running after the job
finished, or job counters that disagree with the item table. Processes updated
during the job but outside the request are reported as warnings.

    python scripts/verify-acquisition.py --db data/atos-tce.db --job 12
    python scripts/verify-acquisition.py --db data/atos-tce.db --job 12 --queue data/queues/acquisition-12.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.store import Store  # noqa: E402
from app.econtas.legacy_queue import FrozenQueueError, read_frozen_queue  # noqa: E402

TERMINAL_STATES = ("DOWNLOADED", "FAILED", "SKIPPED")
QUEUE_TREE = "queues"


class AcquisitionCheckError(RuntimeError):
    """Raised when the check cannot read what it needs."""


def queue_keys(queue_path: Path) -> list[str]:
    """Read the frozen queue the job used, verifying its identity first."""

    if not queue_path.is_file():
        raise AcquisitionCheckError(f"fila congelada ausente: {queue_path}")
    try:
        document = read_frozen_queue(queue_path)
    except FrozenQueueError as error:
        raise AcquisitionCheckError(f"fila congelada ilegível ({queue_path}): {error}") from error
    items = document.get("queue")
    if not isinstance(items, list):
        raise AcquisitionCheckError(f"fila congelada sem lista 'queue': {queue_path}")
    keys: list[str] = []
    for item in items:
        if isinstance(item, dict):
            key = str(item.get("process_key") or "").strip()
        else:
            key = str(item).strip()
        if key:
            keys.append(key)
    return keys


def verify_job(
    database: str | Path,
    job_id: int,
    *,
    queue_path: str | Path | None = None,
) -> dict[str, Any]:
    """Check one acquisition job against the queue it was supposed to run."""

    path = Path(database)
    if not path.is_file():
        raise AcquisitionCheckError(f"banco da Mesa ausente: {path}")
    data_root = path.parent
    queue = Path(queue_path) if queue_path is not None else data_root / QUEUE_TREE / f"acquisition-{int(job_id)}.json"
    requested = queue_keys(queue)

    store = Store.open(path)
    try:
        job = store.get_job(int(job_id))
        if job is None:
            raise AcquisitionCheckError(f"job inexistente: {job_id}")
        items = store.list_job_items(int(job_id))
        processes = {int(row["id"]): row for row in store.list_processes()}
        documents = store.document_counts()
    finally:
        store.close()

    attempted: list[dict[str, Any]] = []
    for item in items:
        process = processes.get(int(item["process_id"]))
        key = str(process["process_key"]) if process else f"process_id={item['process_id']}"
        attempted.append(
            {
                "process_key": key,
                "state": str(item["state"]),
                "error": item.get("error"),
                "documents": int(documents.get(int(item["process_id"]), 0)),
            }
        )

    violations: list[str] = []
    warnings: list[dict[str, Any]] = []
    requested_set = set(requested)
    attempted_set = {item["process_key"] for item in attempted}

    for key in sorted(attempted_set - requested_set):
        violations.append(f"chave baixada sem pedido: {key}")
    for key in sorted(requested_set - attempted_set):
        violations.append(f"chave pedida sem item no job: {key}")

    finished = bool(job.get("finished_at"))
    for item in attempted:
        if finished and item["state"] not in TERMINAL_STATES:
            violations.append(f"item ainda em {item['state']} depois do job terminar: {item['process_key']}")

    downloaded = sum(1 for item in attempted if item["state"] == "DOWNLOADED")
    failed = sum(1 for item in attempted if item["state"] == "FAILED")
    if int(job.get("completed") or 0) != downloaded:
        violations.append(
            f"contadores do job divergem dos itens: completed={job.get('completed')} esperado={downloaded}"
        )
    if int(job.get("failed") or 0) != failed:
        violations.append(
            f"contadores do job divergem dos itens: failed={job.get('failed')} esperado={failed}"
        )

    started_at = str(job.get("started_at") or "")
    if started_at:
        for process in processes.values():
            key = str(process["process_key"])
            if key in requested_set or str(process.get("updated_at") or "") < started_at:
                continue
            warnings.append(
                {
                    "process_key": key,
                    "updated_at": process.get("updated_at"),
                    "acquisition_state": process.get("acquisition_state"),
                    "reason": "processo atualizado durante o job fora do pedido",
                }
            )

    return {
        "job": {
            "id": int(job["id"]),
            "type": job.get("job_type"),
            "status": job.get("status"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
        },
        "queue": {"path": str(queue), "keys": requested},
        "requested": requested,
        "attempted": sorted(attempted_set),
        "items": attempted,
        "counts": {"downloaded": downloaded, "failed": failed, "total": len(attempted)},
        "violations": violations,
        "warnings": warnings,
        "ok": not violations,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", type=Path, required=True, help="Mesa database with jobs and items")
    parser.add_argument("--job", type=int, required=True, help="acquisition job id")
    parser.add_argument(
        "--queue",
        type=Path,
        default=None,
        help="frozen queue the job used (default: <db folder>/queues/acquisition-<job>.json)",
    )
    parser.add_argument("--json", type=Path, default=None, help="also write the report to this file")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - host stream dependent
                pass
    args = build_parser().parse_args(argv)
    try:
        report = verify_job(args.db, args.job, queue_path=args.queue)
    except AcquisitionCheckError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
