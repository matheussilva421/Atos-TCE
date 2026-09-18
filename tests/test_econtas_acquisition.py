"""Tests for Mesa-controlled e-Contas acquisition (M3)."""

import json
import hashlib
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.jobs import ACQUISITION_STATES, JOB_STATUSES, JobManager
from app.core.store import SCHEMA_V1, SCHEMA_V2, Store
from app.econtas.legacy_queue import (
    FrozenQueueError,
    read_frozen_queue,
    write_frozen_queue,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_APP_DIR = REPO_ROOT / "work" / "tce-extractor" / "portable" / "app"


def legacy_load_frozen_queue(path, lot_number=None):
    """Load the proven validator exactly as the collector does."""

    if str(LEGACY_APP_DIR) not in sys.path:
        sys.path.insert(0, str(LEGACY_APP_DIR))
    import importlib

    module = importlib.import_module("frozen_queue")
    if lot_number is None:
        return module.load_frozen_queue(Path(path))
    return module.load_frozen_queue(Path(path), lot_number=lot_number)


def powershell_read_frozen_queue(path):
    script = (
        "Import-Module '.\\work\\tce-extractor\\portable\\TceFrozenQueue.psm1'; "
        f"Read-TceFrozenQueue -Path '{path}' | ConvertTo-Json -Depth 10 -Compress"
    )
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def seed_pending(store, keys, *, classification="PRECISA_COMPLEMENTAR"):
    """Create processes the way a real Área Restrita scan would."""

    rows = [
        {
            "process_key": key,
            "interested": "Pessoa Exemplo",
            "interested_normalized": "pessoa exemplo",
            "classification": classification,
            "needs_complement": classification == "PRECISA_COMPLEMENTAR",
        }
        for key in keys
    ]
    store.create_area_scan(
        source_scope="sector_finalistic",
        marker_label="PROFESSOR - IPERN - 2 RUBRICAS",
        marker_value="6189",
        rows=rows,
    )
    return store.list_processes()


class AcquisitionTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.manager = JobManager(self.store)


class JobStateTests(AcquisitionTestCase):
    def test_job_tracks_completed_and_failed_items(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026"])
        job_id = self.manager.create("acquisition", [row["id"] for row in rows])
        self.manager.start(job_id)
        self.manager.mark_item(job_id, rows[0]["id"], "DOWNLOADED")
        self.manager.mark_item(job_id, rows[1]["id"], "FAILED", "auth required")
        self.manager.finish(job_id)

        job = self.store.get_job(job_id)

        self.assertEqual(job["completed"], 1)
        self.assertEqual(job["failed"], 1)
        self.assertEqual(job["status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(job["total"], 2)

    def test_a_new_job_starts_pending_with_its_items(self):
        rows = seed_pending(self.store, ["102390/2026"])

        job_id = self.manager.create("acquisition", [rows[0]["id"]])

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "PENDING")
        self.assertEqual(job["total"], 1)
        self.assertEqual(job["job_type"], "acquisition")
        items = self.store.list_job_items(job_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["state"], "QUEUED")

    def test_start_records_running_and_started_at(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])

        self.manager.start(job_id)

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "RUNNING")
        self.assertTrue(job["started_at"])

    def test_finish_without_failures_is_completed(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026"])
        job_id = self.manager.create("acquisition", [row["id"] for row in rows])
        self.manager.start(job_id)
        for row in rows:
            self.manager.mark_item(job_id, row["id"], "DOWNLOADED")

        self.manager.finish(job_id)

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(job["completed"], 2)
        self.assertEqual(job["failed"], 0)
        self.assertTrue(job["finished_at"])

    def test_marking_an_item_updates_the_process_acquisition_state(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)

        self.manager.mark_item(job_id, rows[0]["id"], "DOWNLOADED")
        self.assertEqual(self.store.get_process(rows[0]["id"])["acquisition_state"], "DOWNLOADED")

        self.manager.mark_item(job_id, rows[0]["id"], "FAILED", "portal sem login")
        process = self.store.get_process(rows[0]["id"])
        self.assertEqual(process["acquisition_state"], "FAILED")

    def test_repeating_an_item_state_keeps_one_row(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)

        self.manager.mark_item(job_id, rows[0]["id"], "DOWNLOADING")
        self.manager.mark_item(job_id, rows[0]["id"], "DOWNLOADED")

        items = self.store.list_job_items(job_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["state"], "DOWNLOADED")
        self.assertEqual(items[0]["error"], None)

    def test_failed_item_keeps_its_error_message(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)

        self.manager.mark_item(job_id, rows[0]["id"], "FAILED", "tempo esgotado")

        self.assertEqual(self.store.list_job_items(job_id)[0]["error"], "tempo esgotado")

    def test_an_unknown_state_is_refused(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])

        with self.assertRaises(ValueError):
            self.manager.mark_item(job_id, rows[0]["id"], "TALVEZ")

    def test_marking_an_unknown_process_is_refused(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])

        with self.assertRaises(ValueError):
            self.manager.mark_item(job_id, 4242, "DOWNLOADED")

    def test_pausing_a_job_records_waiting_for_login(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)

        self.manager.wait_for_login(job_id, "e-Contas pediu login")

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "WAITING_FOR_LOGIN")
        self.assertEqual(job["error"], "e-Contas pediu login")
        self.assertIn("WAITING_FOR_LOGIN", JOB_STATUSES)

    def test_the_published_vocabularies_are_stable(self):
        self.assertEqual(
            ACQUISITION_STATES, ("NOT_DOWNLOADED", "QUEUED", "DOWNLOADING", "DOWNLOADED", "FAILED")
        )
        self.assertEqual(len(set(ACQUISITION_STATES)), len(ACQUISITION_STATES))


class MissingPendingSelectionTests(AcquisitionTestCase):
    def test_only_pending_processes_without_bytes_are_selected(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026", "102392/2026"])
        self.manager.mark_downloaded(rows[0]["id"])

        selected = self.store.list_missing_pending_processes()

        self.assertEqual([row["process_key"] for row in selected], ["102391/2026", "102392/2026"])

    def test_completed_and_ambiguous_processes_are_never_selected(self):
        self.store.create_area_scan(
            source_scope="sector_finalistic",
            marker_label="M",
            marker_value="1",
            rows=[
                {
                    "process_key": "102390/2026",
                    "interested": "Pessoa Exemplo",
                    "interested_normalized": "pessoa exemplo",
                    "classification": "ATO_COMPLEMENTADO",
                    "needs_complement": False,
                },
                {
                    "process_key": "102391/2026",
                    "interested": "Outra Pessoa",
                    "interested_normalized": "outra pessoa",
                    "classification": "AMBIGUO",
                    "needs_complement": False,
                },
                {
                    "process_key": "102392/2026",
                    "interested": "Terceira Pessoa",
                    "interested_normalized": "terceira pessoa",
                    "classification": "PRECISA_COMPLEMENTAR",
                    "needs_complement": True,
                },
            ],
        )

        selected = self.store.list_missing_pending_processes()

        self.assertEqual([row["process_key"] for row in selected], ["102392/2026"])

    def test_a_failed_download_is_selected_again(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)
        self.manager.mark_item(job_id, rows[0]["id"], "FAILED", "rede")

        self.assertEqual(len(self.store.list_missing_pending_processes()), 1)

    def test_selection_keeps_the_area_scan_order(self):
        seed_pending(self.store, ["105000/2025", "100100/2026", "103000/2024"])

        selected = self.store.list_missing_pending_processes()

        self.assertEqual(
            [row["process_key"] for row in selected],
            ["105000/2025", "100100/2026", "103000/2024"],
        )


class FrozenQueueWriterTests(AcquisitionTestCase):
    def setUp(self):
        super().setUp()
        self.queue_path = self.data / "queues" / "fila-congelada.json"

    def write(self, keys, *, lot_size=50, source_scope="sector_finalistic", marker=None):
        return write_frozen_queue(
            [{"process_key": key} for key in keys],
            source_scope,
            marker if marker is not None else {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"},
            self.queue_path,
            lot_size,
        )

    def test_the_legacy_loader_accepts_the_written_queue(self):
        info = self.write(["102390/2026", "102391/2026"], lot_size=1)

        loaded = legacy_load_frozen_queue(self.queue_path)

        self.assertEqual(
            [item["process_key"] for item in loaded["items"]], ["102390/2026", "102391/2026"]
        )
        self.assertEqual(info.lot_count, 2)
        self.assertEqual(loaded["analysis_id"], info.analysis_id)
        self.assertEqual(loaded["dataset_sha256"], info.dataset_sha256)
        self.assertEqual(loaded["source_scope"], "sector_finalistic")
        self.assertEqual(loaded["marker"], {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"})
        self.assertEqual(loaded["queue_size"], 2)

    def test_hash_and_analysis_id_come_from_the_canonical_json(self):
        info = self.write(["102390/2026"])

        document = json.loads(self.queue_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(document["canonical_json"].encode("utf-8")).hexdigest()

        self.assertEqual(digest, info.dataset_sha256)
        self.assertEqual(document["analysis_id"], f"analysis-{digest[:24]}")
        self.assertEqual(document["schema_version"], 3)
        canonical = json.loads(document["canonical_json"])
        self.assertEqual(
            sorted(canonical), ["blocked", "observed_at", "queue", "schema_version", "spec"]
        )
        self.assertEqual(canonical["spec"]["acquisition_source"], "econtas")
        self.assertEqual(canonical["blocked"], [])

    def test_ninety_two_processes_become_two_lots_of_fifty_and_forty_two(self):
        keys = [f"{100000 + index}/2026" for index in range(92)]

        info = self.write(keys, lot_size=50)

        self.assertEqual(info.queue_size, 92)
        self.assertEqual(info.lot_count, 2)
        loaded = legacy_load_frozen_queue(self.queue_path)
        self.assertEqual(len(loaded["items"]), 92)
        second = legacy_load_frozen_queue(self.queue_path, 2)
        self.assertEqual(len(second["items"]), 42)
        self.assertEqual(second["items"][0]["process_key"], "100050/2026")

    def test_duplicate_keys_are_collapsed_keeping_the_first_position(self):
        info = self.write(["102391/2026", "102390/2026", "102391/2026"])

        self.assertEqual(info.queue_size, 2)
        loaded = legacy_load_frozen_queue(self.queue_path)
        self.assertEqual(
            [item["process_key"] for item in loaded["items"]], ["102391/2026", "102390/2026"]
        )

    def test_a_non_numeric_key_is_refused(self):
        with self.assertRaises(FrozenQueueError):
            self.write(["processo-invalido"])

    def test_an_unsupported_scope_is_refused(self):
        with self.assertRaises(FrozenQueueError):
            self.write(["102390/2026"], source_scope="outro_setor")

    def test_an_empty_plan_is_refused(self):
        with self.assertRaises(FrozenQueueError):
            self.write([])

    def test_the_powershell_validator_reads_the_same_queue(self):
        self.write(["102390/2026", "102391/2026"], lot_size=1)

        result = powershell_read_frozen_queue(self.queue_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["queue_size"], 2)
        self.assertEqual(payload["source_scope"], "sector_finalistic")

    def test_reading_back_detects_tampering(self):
        info = self.write(["102390/2026"])
        self.assertEqual(read_frozen_queue(self.queue_path)["analysis_id"], info.analysis_id)

        tampered = json.loads(self.queue_path.read_text(encoding="utf-8"))
        tampered["queue"] = [{"process_key": "999999/2026"}]
        self.queue_path.write_text(json.dumps(tampered), encoding="utf-8")

        with self.assertRaises(FrozenQueueError):
            read_frozen_queue(self.queue_path)


class SchemaV3MigrationTests(unittest.TestCase):
    def build_v2_database(self, database: Path) -> None:
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for statement in SCHEMA_V1:
            connection.execute(statement)
        for statement in SCHEMA_V2:
            connection.execute(statement)
        connection.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '2')")
        connection.execute(
            "INSERT INTO processes (process_key, interested, interested_normalized, status, created_at, updated_at) "
            "VALUES ('102390/2026', 'Pessoa Exemplo', 'pessoa exemplo', 'PENDENTE', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO area_scans (source_scope, marker_label, marker_value, observed_at, origin, total) "
            "VALUES ('sector_finalistic', 'M', '6189', '2026-01-01T00:00:00Z', 'extension', 1)"
        )
        connection.commit()
        connection.close()

    def test_migration_from_v2_adds_acquisition_state_and_preserves_rows(self):
        with TemporaryDirectory() as tmp:
            database = Path(tmp) / "atos-tce.db"
            self.build_v2_database(database)

            store = Store.open(database)
            try:
                self.assertEqual(store.schema_version, 3)
                processes = store.list_processes()
                self.assertEqual(len(processes), 1)
                self.assertEqual(processes[0]["acquisition_state"], "NOT_DOWNLOADED")
                self.assertEqual(store.get_area_scan(1)["total"], 1)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
