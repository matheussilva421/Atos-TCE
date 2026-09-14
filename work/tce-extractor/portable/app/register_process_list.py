"""CLI used by the portable menu to register an authoritative workbook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from process_list import ProcessListStore, import_process_workbook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="registra a planilha autoritativa do TCE")
    parser.add_argument("--root", type=Path, required=True, help="raiz acervo-tce")
    parser.add_argument("--input", type=Path, required=True, help="arquivo .xlsx de entrada")
    args = parser.parse_args(argv)
    manifest = ProcessListStore(args.root).save(import_process_workbook(args.input))
    print(json.dumps({
        "input_list_id": manifest["input_list_id"],
        "input_sha256": manifest["input_sha256"],
        "row_count": manifest["row_count"],
        "unique_count": manifest["unique_count"],
        "duplicate_count": manifest["duplicate_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Falha ao importar lista: {error}", file=sys.stderr)
        raise SystemExit(2)
