"""Root package layout and SQLite store tests for the new Mesa application."""

import importlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import DocumentRecord, FieldRecord, ProcessRecord
from app.core.store import Store


class PackageLayoutTests(unittest.TestCase):
    def test_packages_import(self):
        for name in ("app", "app.core", "app.archive", "app.api"):
            self.assertIsNotNone(importlib.import_module(name))


def sample_process(**overrides):
    values = {
        "process_key": "102390/2026",
        "interested": "Pessoa Exemplo",
        "interested_normalized": "pessoa exemplo",
        "source_scope": "sector_finalistic",
        "marker": "PROFESSOR - IPERN - 2 RUBRICAS",
        "status": "PRONTO",
    }
    values.update(overrides)
    return ProcessRecord(**values)


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data_root / "atos-tce.db")
        self.addCleanup(self.store.close)


class StoreRoundTripTests(StoreTestCase):
    def test_round_trip(self):
        process_id = self.store.upsert_process(sample_process())
        self.store.add_workflow_event(process_id, "analysis_finished", {"status": "PRONTO"})

        loaded = self.store.get_process(process_id)

        self.assertEqual(loaded["process_key"], "102390/2026")
        self.assertEqual(loaded["interested"], "Pessoa Exemplo")
        self.assertEqual(loaded["status"], "PRONTO")
        self.assertEqual(loaded["events"][0]["event_type"], "analysis_finished")
        self.assertEqual(loaded["events"][0]["payload"], {"status": "PRONTO"})
        self.assertEqual(self.store.schema_version, 1)

    def test_open_creates_missing_directories(self):
        self.assertTrue((self.data_root / "atos-tce.db").is_file())

    def test_unknown_process_returns_none(self):
        self.assertIsNone(self.store.get_process(4242))


class StoreUpsertTests(StoreTestCase):
    def test_repeated_upsert_keeps_one_row_and_returns_same_id(self):
        first = self.store.upsert_process(sample_process())
        second = self.store.upsert_process(sample_process(status="REVISAR"))

        self.assertEqual(first, second)
        self.assertEqual(len(self.store.list_processes()), 1)
        self.assertEqual(self.store.get_process(first)["status"], "REVISAR")

    def test_same_key_different_interested_creates_second_row(self):
        first = self.store.upsert_process(sample_process())
        second = self.store.upsert_process(
            sample_process(interested="Outra Pessoa", interested_normalized="outra pessoa")
        )

        self.assertNotEqual(first, second)
        self.assertEqual(len(self.store.list_processes()), 2)

    def test_upsert_keeps_known_scope_when_new_value_is_blank(self):
        process_id = self.store.upsert_process(sample_process())
        self.store.upsert_process(sample_process(source_scope=None, marker=None))

        loaded = self.store.get_process(process_id)
        self.assertEqual(loaded["source_scope"], "sector_finalistic")
        self.assertEqual(loaded["marker"], "PROFESSOR - IPERN - 2 RUBRICAS")


class StoreCollectionTests(StoreTestCase):
    def test_replace_documents_and_fields(self):
        process_id = self.store.upsert_process(sample_process())
        self.store.replace_documents(
            process_id,
            [
                DocumentRecord(
                    source_id="doc-1",
                    event="1",
                    title="Ato.pdf",
                    relative_path="processos/102390-2026/Ato.pdf",
                    sha256="a" * 64,
                    page_count=3,
                    classification="ato",
                    storage_state="HOT",
                )
            ],
        )
        self.store.replace_fields(
            process_id,
            [
                FieldRecord(
                    field_name="cargo",
                    value="Professor",
                    status="found",
                    confidence=1.0,
                    document_id=self.store.get_process(process_id)["documents"][0]["id"],
                    page=2,
                    evidence={"quote": "Professor"},
                )
            ],
        )

        loaded = self.store.get_process(process_id)

        self.assertEqual(len(loaded["documents"]), 1)
        self.assertEqual(loaded["documents"][0]["title"], "Ato.pdf")
        self.assertEqual(loaded["documents"][0]["page_count"], 3)
        self.assertEqual(loaded["fields"][0]["field_name"], "cargo")
        self.assertEqual(loaded["fields"][0]["page"], 2)
        self.assertEqual(loaded["fields"][0]["evidence"], {"quote": "Professor"})

    def test_replace_documents_removes_stale_rows(self):
        process_id = self.store.upsert_process(sample_process())
        document = DocumentRecord(
            source_id="doc-1",
            title="Ato.pdf",
            relative_path="processos/102390-2026/Ato.pdf",
            sha256="a" * 64,
            page_count=3,
        )
        self.store.replace_documents(process_id, [document])
        self.store.replace_documents(process_id, [])

        self.assertEqual(self.store.get_process(process_id)["documents"], [])

    def test_list_processes_filters_by_status(self):
        self.store.upsert_process(sample_process())
        self.store.upsert_process(
            sample_process(
                process_key="102391/2026",
                interested="Outra Pessoa",
                interested_normalized="outra pessoa",
                status="PENDENTE",
            )
        )

        pending = self.store.list_processes(status="PENDENTE")

        self.assertEqual([row["process_key"] for row in pending], ["102391/2026"])
        self.assertEqual(len(self.store.list_processes()), 2)

    def test_storage_summary_counts_rows(self):
        process_id = self.store.upsert_process(sample_process())
        self.store.replace_documents(
            process_id,
            [
                DocumentRecord(
                    source_id="doc-1",
                    title="Ato.pdf",
                    relative_path="processos/102390-2026/Ato.pdf",
                    sha256="a" * 64,
                    page_count=1,
                ),
                DocumentRecord(
                    source_id="doc-2",
                    title="Copia.pdf",
                    relative_path="processos/102390-2026/Copia.pdf",
                    sha256="a" * 64,
                    page_count=1,
                ),
            ],
        )

        summary = self.store.storage_summary()

        self.assertEqual(summary["processes"]["total"], 1)
        self.assertEqual(summary["processes"]["by_status"], {"PRONTO": 1})
        self.assertEqual(summary["documents"]["total"], 2)
        self.assertEqual(summary["documents"]["unique_sha256"], 1)

    def test_workflow_events_keep_insertion_order(self):
        process_id = self.store.upsert_process(sample_process())
        self.store.add_workflow_event(process_id, "download_finished", {})
        self.store.add_workflow_event(process_id, "analysis_started", {})

        events = self.store.get_process(process_id)["events"]

        self.assertEqual([event["event_type"] for event in events], ["download_finished", "analysis_started"])


if __name__ == "__main__":
    unittest.main()
