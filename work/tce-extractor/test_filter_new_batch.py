import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "portable" / "app" / "filter_new_batch.py"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checkpoint(processes: list[dict], documents: list[dict]) -> dict:
    return {
        "version": 1,
        "updated_at": "2026-09-04T00:00:00Z",
        "processes": processes,
        "documents": documents,
    }


class FilterNewBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="tce-filter-new-batch-")
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source"
        self.baseline = self.root / "baseline"
        self.source_processes: list[dict] = []
        self.source_documents: list[dict] = []

        for index in range(62):
            key = f"{100000 + index}/2024"
            if index < 50:
                process = {
                    "key": key,
                    "number": str(100000 + index),
                    "year": 2024,
                    "id": f"current-id-{index}",
                    "status": "complete",
                }
                self.source_processes.append(process)
                folder = self.source / "processos" / f"{100000 + index}-2024"
                event_folder = folder / "evento-0001-1"
                pdf_path = event_folder / f"documento-001-processo-{index}.pdf"
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(f"%PDF-current-{index}\n".encode())
                write_json(
                    folder / "processo.json",
                    {"key": key, "number": str(100000 + index), "year": 2024, "events": []},
                )
                write_json(
                    event_folder / "evento.json",
                    {"event": 1, "event_id": "1", "documents": []},
                )
                self.source_documents.append(
                    {
                        "key": f"{key}|1|doc-{index}",
                        "id": f"doc-{index}",
                        "title": f"Processo {index}",
                        "path": str(pdf_path.relative_to(self.source)).replace("\\", "/"),
                        "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                        "status": "complete",
                    }
                )
        baseline_processes = [
            {
                "key": f" {100000 + index} / 2024 " if index < 7 else f"200000{index}/2024",
                "number": str(100000 + index) if index < 7 else f"200000{index}",
                "year": 2024,
                "id": f"historical-id-{index}",
                "status": "partial" if index < 4 else "complete",
                "note": "baseline-token=must-not-be-copied",
            }
            for index in range(62)
        ]
        write_json(self.source / "checkpoint.json", checkpoint(self.source_processes, self.source_documents))
        write_json(self.source / "README.txt", {"scope": "current source only"})
        write_json(self.baseline / "checkpoint.json", checkpoint(baseline_processes, []))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def make_baseline_zip(self, name: str = "baseline.zip") -> Path:
        zip_path = self.root / name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(self.baseline / "checkpoint.json", "acervo-tce/checkpoint.json")
        return zip_path

    def run_filter(
        self,
        baseline: Path,
        output: Path,
        source: Path | None = None,
        baseline_all_complete: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        source = source or self.source
        command = [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--baseline",
            str(baseline),
            "--output",
            str(output),
        ]
        if baseline_all_complete:
            command.append("--baseline-all-complete")
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_default_uses_only_complete_baseline_records(self) -> None:
        output = self.root / "filtered-default"
        source_before = {
            path.relative_to(self.source): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        }

        result = self.run_filter(self.baseline, output)

        self.assertEqual(result.returncode, 0, result.stderr)
        filtered_checkpoint = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
        kept_keys = [record["key"] for record in filtered_checkpoint["processes"]]
        self.assertEqual(len(self.source_processes), 50)
        self.assertEqual(len(kept_keys), 47)
        self.assertEqual(
            kept_keys,
            [f"{100000 + index}/2024" for index in [*range(4), *range(7, 50)]],
        )
        self.assertEqual(len(filtered_checkpoint["documents"]), 47)
        self.assertEqual(len({document["path"] for document in filtered_checkpoint["documents"]}), 47)
        output_pdfs = sorted((output / "processos").glob("**/*.pdf"))
        self.assertEqual(len(output_pdfs), 47)
        for index in range(4, 7):
            self.assertFalse((output / "processos" / f"{100000 + index}-2024").exists())
        for index in [*range(4), *range(7, 50)]:
            self.assertTrue((output / "processos" / f"{100000 + index}-2024" / "evento-0001-1" / f"documento-001-processo-{index}.pdf").is_file())
        self.assertEqual(source_before, {
            path.relative_to(self.source): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        })

    def test_baseline_all_complete_filters_all_seven_overlaps_to_43(self) -> None:
        output = self.root / "filtered-all-complete"
        baseline_zip = self.make_baseline_zip("baseline-all-complete.zip")
        source_before = {
            path.relative_to(self.source): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        }

        result = self.run_filter(baseline_zip, output, baseline_all_complete=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        filtered_checkpoint = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
        kept_keys = [record["key"] for record in filtered_checkpoint["processes"]]
        self.assertEqual(len(self.source_processes), 50)
        self.assertEqual(len(kept_keys), 43)
        self.assertEqual(kept_keys, [f"{100000 + index}/2024" for index in range(7, 50)])
        self.assertEqual(len(filtered_checkpoint["documents"]), 43)
        self.assertEqual(len({document["path"] for document in filtered_checkpoint["documents"]}), 43)
        output_pdfs = sorted((output / "processos").glob("**/*.pdf"))
        self.assertEqual(len(output_pdfs), 43)
        for index in range(7):
            self.assertFalse((output / "processos" / f"{100000 + index}-2024").exists())
        for index in range(7, 50):
            self.assertTrue((output / "processos" / f"{100000 + index}-2024" / "evento-0001-1" / f"documento-001-processo-{index}.pdf").is_file())
        output_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in output.rglob("*") if path.is_file())
        self.assertNotIn("baseline-token", output_text)
        self.assertNotIn("Bearer ", output_text)
        self.assertNotIn("cookie=", output_text)
        self.assertEqual(source_before, {
            path.relative_to(self.source): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        })
        self.assertTrue(baseline_zip.is_file())

    def test_rejects_existing_output_and_invalid_document_path(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "sentinel.txt"
        sentinel.write_text("preserve", encoding="utf-8")

        result = self.run_filter(self.baseline, output)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output", result.stderr.lower())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

        invalid_source = self.root / "invalid-source"
        invalid_source.mkdir()
        write_json(invalid_source / "checkpoint.json", checkpoint(self.source_processes, [{
            "key": "100000/2024|1|bad",
            "path": "../outside.pdf",
            "status": "complete",
        }]))
        invalid_result = self.run_filter(self.baseline, self.root / "invalid-output", invalid_source)
        self.assertNotEqual(invalid_result.returncode, 0)

    def test_accepts_checkpoint_file_and_private_zip_baseline(self) -> None:
        baseline_checkpoint = self.baseline / "checkpoint.json"
        zip_path = self.make_baseline_zip()

        for baseline in (baseline_checkpoint, zip_path):
            with self.subTest(baseline=baseline.name):
                result = self.run_filter(baseline, self.root / f"filtered-{baseline.suffix[1:] or 'file'}")
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
