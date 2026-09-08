import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from archive_index import scan_archive, write_index


def make_archive(root: Path, *, layout: str, events: list[dict]) -> Path:
    archive = root / "acervo-tce"
    process_root = archive / "processos" if layout == "new" else archive
    process_dir = process_root / "103439-2023"
    process_dir.mkdir(parents=True)

    process_events = []
    for event_data in events:
        event_number = event_data["event"]
        event_id = event_data["event_id"]
        event_dir = process_dir / f"evento-{event_number:04d}-{event_id}"
        event_dir.mkdir()
        documents = []
        for ordinal, (filename, payload) in enumerate(event_data["files"], start=1):
            document_path = event_dir / filename
            document_path.write_bytes(payload)
            documents.append(
                {
                    "id": f"doc-{event_number}-{ordinal}",
                    "title": filename,
                    "extension": document_path.suffix,
                    "path": document_path.relative_to(archive).as_posix(),
                    "status": "complete",
                    "url": "https://tce.invalid/temporary-download?token=secret",
                }
            )
        event = {
            "event": event_number,
            "event_id": event_id,
            "date": event_data.get("date", "2023-04-28T12:02:10"),
            "title": event_data.get("title", f"Evento {event_number}"),
            "active": True,
            "documents": documents,
        }
        (event_dir / "evento.json").write_text(
            json.dumps(event), encoding="utf-8"
        )
        process_events.append(event)

    process = {
        "key": "103439/2023",
        "id": "582647",
        "number": "103439",
        "year": 2023,
        "status": "complete",
        "events": process_events,
        "url": "https://tce.invalid/processo/582647",
    }
    (process_dir / "processo.json").write_text(
        json.dumps(process), encoding="utf-8"
    )
    return archive


class ArchiveIndexTests(unittest.TestCase):
    def test_scan_archive_new_layout_hashes_documents_and_preserves_empty_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = make_archive(
                Path(temporary),
                layout="new",
                events=[
                    {"event": 1, "event_id": 9001, "files": [("resolucao.pdf", b"%PDF-fixture")]},
                    {"event": 2, "event_id": 9002, "files": []},
                ],
            )

            index = scan_archive(archive)

            self.assertEqual(index["version"], 1)
            self.assertEqual(len(index["processes"]), 1)
            process = index["processes"][0]
            self.assertEqual(process["key"], "103439/2023")
            self.assertEqual(process["events"][1]["documents"], [])
            document = process["events"][0]["documents"][0]
            self.assertEqual(document["sha256"], hashlib.sha256(b"%PDF-fixture").hexdigest())
            self.assertEqual(
                document["relative_path"],
                "processos/103439-2023/evento-0001-9001/resolucao.pdf",
            )
            self.assertEqual(document["status"], "complete")
            self.assertNotIn("url", json.dumps(index).lower())

    def test_scan_archive_reads_legacy_processes_directly_under_archive_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = make_archive(
                Path(temporary),
                layout="legacy",
                events=[{"event": 9, "event_id": 4987340, "files": [("anexo.pdf", b"legacy")] }],
            )

            index = scan_archive(archive)

            document = index["processes"][0]["events"][0]["documents"][0]
            self.assertEqual(
                document["relative_path"],
                "103439-2023/evento-0009-4987340/anexo.pdf",
            )
            self.assertEqual(document["sha256"], hashlib.sha256(b"legacy").hexdigest())

    def test_write_index_persists_sanitized_index_atomically(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = make_archive(
                root,
                layout="new",
                events=[{"event": 1, "event_id": 9001, "files": []}],
            )
            output = archive / "indice-local.json"
            output.write_text("old index", encoding="utf-8")

            returned = write_index(archive, output)

            self.assertTrue(output.is_file())
            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(persisted, returned)
            self.assertNotIn("url", output.read_text(encoding="utf-8").lower())

    def test_scan_archive_rejects_external_previous_paths_and_nested_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = make_archive(
                root,
                layout="new",
                events=[{"event": 1, "event_id": 9001, "files": [("anexo.pdf", b"payload")]}],
            )
            event_json = archive / "processos" / "103439-2023" / "evento-0001-9001" / "evento.json"
            event = json.loads(event_json.read_text(encoding="utf-8"))
            event["documents"][0].update(
                {
                    "title": "Título https://tce.invalid/file Authorization: Bearer title-secret",
                    "remote_signature": "token=signature-secret",
                    "previous_versions": [
                        {
                            "sha256": "a" * 64,
                            "path": str(root / "outside.pdf"),
                            "metadata": {
                                "cookie": "nested-cookie-secret",
                                "token": "nested-token-secret",
                            },
                        },
                        {
                            "sha256": "b" * 64,
                            "path": "processos/103439-2023/versao-anterior.pdf",
                            "metadata": {"url": "https://tce.invalid/nested"},
                        },
                    ],
                }
            )
            event_json.write_text(json.dumps(event), encoding="utf-8")

            index = scan_archive(archive)
            document = index["processes"][0]["events"][0]["documents"][0]
            serialized = json.dumps(index)

            self.assertNotIn("title-secret", serialized)
            self.assertNotIn("signature-secret", serialized)
            self.assertNotIn("nested-cookie-secret", serialized)
            self.assertNotIn("nested-token-secret", serialized)
            self.assertNotIn("outside.pdf", serialized)
            self.assertEqual(
                document["previous_versions"],
                [
                    {
                        "sha256": "b" * 64,
                        "path": "processos/103439-2023/versao-anterior.pdf",
                        "metadata": {},
                    }
                ],
            )

    def test_write_index_rejects_destination_outside_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = make_archive(
                root,
                layout="new",
                events=[{"event": 1, "event_id": 9001, "files": []}],
            )

            with self.assertRaises(ValueError):
                write_index(archive, root / "indice-fora-do-acervo.json")

    def test_scan_archive_marks_unavailable_documents_missing_without_persisting_url_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = make_archive(
                Path(temporary),
                layout="new",
                events=[{"event": 1, "event_id": 9001, "files": [("anexo.pdf", b"orphan")] }],
            )
            event_json = archive / "processos" / "103439-2023" / "evento-0001-9001" / "evento.json"
            event = json.loads(event_json.read_text(encoding="utf-8"))
            event["documents"][0]["path"] = "https://tce.invalid/temporary-download?token=secret"
            event_json.write_text(json.dumps(event), encoding="utf-8")

            index = scan_archive(archive)

            document = index["processes"][0]["events"][0]["documents"][0]
            self.assertIsNone(document["relative_path"])
            self.assertIsNone(document["sha256"])
            self.assertEqual(document["status"], "missing")
            self.assertNotIn("url", json.dumps(index).lower())

    def test_scan_archive_rejects_corrupt_persisted_order_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = make_archive(
                Path(temporary),
                layout="new",
                events=[{"event": 1, "event_id": 9001, "files": []}],
            )
            (archive / "ordem-portal.json").write_text(
                json.dumps({"schema_version": 1, "captured_at": "", "process_keys": []}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                scan_archive(archive)

    def test_scan_archive_does_not_index_pdf_through_internal_reparse_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = make_archive(
                Path(temporary),
                layout="new",
                events=[{"event": 1, "event_id": 9001, "files": [("real.pdf", b"payload")]}],
            )
            event_dir = archive / "processos" / "103439-2023" / "evento-0001-9001"
            alias = event_dir / "alias.pdf"
            real = event_dir / "real.pdf"
            try:
                os.symlink(real, alias)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"ambiente sem criação de symlink: {exc}")
            event_json = event_dir / "evento.json"
            event = json.loads(event_json.read_text(encoding="utf-8"))
            event["documents"][0]["path"] = alias.relative_to(archive).as_posix()
            event_json.write_text(json.dumps(event), encoding="utf-8")

            index = scan_archive(archive)

            document = index["processes"][0]["events"][0]["documents"][0]
            self.assertIsNone(document["relative_path"])
            self.assertIsNone(document["sha256"])
            self.assertEqual(document["status"], "missing")


if __name__ == "__main__":
    unittest.main()
