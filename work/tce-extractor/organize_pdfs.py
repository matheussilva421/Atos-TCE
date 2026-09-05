"""Organize PDFs downloaded by the browser extension without opening/analyzing them."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from tempfile import NamedTemporaryFile
from typing import Iterable, Sequence


_PDF_NAME = re.compile(
    r"^(?P<number>\d{5,6})[-_](?P<year>\d{4})[-_](?:evento|event)[-_]?(?P<event>\d+)(?:--(?P<copy>\d+))?\.pdf$",
    re.IGNORECASE,
)


def parse_pdf_name(name: str) -> tuple[str, str] | None:
    match = _PDF_NAME.match(Path(name).name)
    if not match:
        return None
    return f"{match.group('number')}/{match.group('year')}", match.group("event")


def _is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(payload, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _process_key(process: str) -> str:
    return process.replace("/", "-")


def organize_pdf_files(
    incoming_dir: Path,
    organized_dir: Path,
    manifest_path: Path,
    *,
    processes: Sequence[str] | None = None,
) -> dict[str, int]:
    incoming = Path(incoming_dir).resolve()
    organized = Path(organized_dir).resolve()
    manifest_file = Path(manifest_path)
    process_ids = list(dict.fromkeys(str(item) for item in (processes or [])))
    by_process: dict[str, list[dict[str, str]]] = {item: [] for item in process_ids}
    files_seen = 0
    organized_count = 0
    unrecognized = 0
    used_names: dict[tuple[str, str], int] = {}

    if not incoming.exists():
        raise FileNotFoundError(f"Pasta de entrada não existe: {incoming}")

    for source in sorted(incoming.rglob("*")):
        if not source.is_file() or organized == source or organized in source.parents:
            continue
        files_seen += 1
        if not _is_pdf(source):
            continue
        parsed = parse_pdf_name(source.name)
        if not parsed:
            unrecognized += 1
            continue
        process, event = parsed
        if process not in by_process:
            by_process[process] = []
            process_ids.append(process)
        key = (process, event)
        copy_number = used_names.get(key, 0) + 1
        used_names[key] = copy_number
        suffix = "" if copy_number == 1 else f"--{copy_number}"
        destination_dir = organized / _process_key(process)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"evento-{int(event):04d}{suffix}.pdf"
        shutil.copy2(source, destination)
        by_process[process].append(
            {
                "event": event,
                "date": "",
                "title": "",
                "pdf_path": str(destination),
                "source_file": source.name,
            }
        )
        organized_count += 1

    processes_payload = []
    for process in process_ids:
        documents = sorted(
            by_process.get(process, []),
            key=lambda item: (int(item["event"]), item["pdf_path"]),
        )
        processes_payload.append({"process": process, "documents": documents})
    payload = {
        "version": 1,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "browser-downloads",
        "processes": processes_payload,
    }
    _atomic_json(manifest_file, payload)
    return {
        "files_seen": files_seen,
        "pdfs_organized": organized_count,
        "unrecognized": unrecognized,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incoming", type=Path, required=True)
    parser.add_argument("--organized", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--process-list",
        type=Path,
        help="JSON com processos no formato {\"processes\":[{\"process\":\"N/A\"}]}.",
    )
    args = parser.parse_args()
    processes = None
    if args.process_list:
        process_payload = json.loads(args.process_list.read_text(encoding="utf-8"))
        processes = [str(item["process"]) for item in process_payload.get("processes", [])]
    print(
        json.dumps(
            organize_pdf_files(
                args.incoming,
                args.organized,
                args.manifest,
                processes=processes,
            ),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
