"""Tests for Área Restrita scans and extension commands (M2 Task 1)."""

import sqlite3
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.api.views import area_summary_payload
from app.core.models import ProcessRecord
from app.core.store import SCHEMA_V1, SCHEMA_VERSION, Store

MARKER_LABEL = "PROFESSOR - IPERN - 2 RUBRICAS"


def row(**overrides):
    values = {
        "process_key": "102390/2026",
        "interested": "Pessoa Exemplo",
        "interested_normalized": "pessoa exemplo",
        "portal_act_id": "123",
        "classification": "PRECISA_COMPLEMENTAR",
        "needs_complement": True,
        "action_observed": "Complementar Ato",
    }
    values.update(overrides)
    return values


class AreaScanTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)

    def scan(self, rows, **overrides):
        arguments = {
            "source_scope": "sector_finalistic",
            "marker_label": MARKER_LABEL,
            "marker_value": "6189",
            "rows": rows,
        }
        arguments.update(overrides)
        return self.store.create_area_scan(**arguments)


class AreaScanMappingTests(AreaScanTestCase):
    def test_pending_row_maps_to_pendente_and_counts(self):
        scan_id = self.scan([row()])

        scan = self.store.get_area_scan(scan_id)

        self.assertEqual(scan["total"], 1)
        self.assertEqual(scan["pending"], 1)
        self.assertEqual(scan["completed"], 0)
        self.assertEqual(scan["source_scope"], "sector_finalistic")
        self.assertEqual(scan["marker_label"], MARKER_LABEL)
        self.assertEqual(scan["marker_value"], "6189")
        self.assertEqual(len(scan["items"]), 1)
        self.assertEqual(scan["items"][0]["classification"], "PRECISA_COMPLEMENTAR")

        process = self.store.list_processes()[0]
        self.assertEqual(process["status"], "PENDENTE")
        self.assertEqual(process["needs_complement"], 1)
        self.assertEqual(process["portal_act_id"], "123")
        self.assertEqual(process["area_classification"], "PRECISA_COMPLEMENTAR")
        self.assertEqual(process["last_area_scan_id"], scan_id)

    def test_completed_row_maps_to_concluido_with_workflow_event(self):
        self.scan([row()])

        self.scan(
            [
                row(
                    classification="ATO_COMPLEMENTADO",
                    needs_complement=False,
                    action_observed="Ato Complementado",
                )
            ]
        )

        process = self.store.list_processes()[0]
        self.assertEqual(process["status"], "CONCLUÍDO")
        self.assertEqual(process["needs_complement"], 0)
        events = self.store.get_process(process["id"])["events"]
        self.assertEqual(events[-1]["event_type"], "portal_completed")

    def test_ambiguous_never_becomes_pronto(self):
        self.scan([row(classification="AMBIGUO", needs_complement=False)])

        process = self.store.list_processes()[0]
        self.assertEqual(process["status"], "PENDENTE")
        self.assertEqual(process["area_classification"], "AMBIGUO")
        self.assertNotEqual(process["status"], "PRONTO")

    def test_blocked_row_is_marked_bloqueado(self):
        self.scan([row(classification="BLOQUEADO", needs_complement=False)])

        self.assertEqual(self.store.list_processes()[0]["status"], "BLOQUEADO")

    def test_not_found_row_stays_pending_without_queueing_a_download(self):
        self.scan([row(classification="NAO_ENCONTRADO_AREA_RESTRITA", needs_complement=False)])

        process = self.store.list_processes()[0]
        self.assertEqual(process["status"], "PENDENTE")
        self.assertEqual(process["needs_complement"], 0)

    def test_unknown_classification_is_pending_and_recorded(self):
        self.scan([row(classification="ALGO_NOVO", needs_complement=False)])

        process = self.store.list_processes()[0]
        self.assertEqual(process["status"], "PENDENTE")
        self.assertNotEqual(process["status"], "PRONTO")

    def test_a_more_advanced_state_is_not_regressed(self):
        process_id = self.store.upsert_process(
            ProcessRecord(
                process_key="102390/2026",
                interested="Pessoa Exemplo",
                interested_normalized="pessoa exemplo",
                status="PREENCHIDO",
            )
        )

        self.scan([row()])

        process = self.store.get_process(process_id)
        self.assertEqual(process["status"], "PREENCHIDO")
        self.assertEqual(process["needs_complement"], 1)
        self.assertEqual(process["area_classification"], "PRECISA_COMPLEMENTAR")

    def test_completed_overrides_an_earlier_extraordinary_state(self):
        self.scan([row(classification="BLOQUEADO", needs_complement=False)])
        self.assertEqual(self.store.list_processes()[0]["status"], "BLOQUEADO")

        self.scan([row(classification="ATO_COMPLEMENTADO", needs_complement=False)])

        self.assertEqual(self.store.list_processes()[0]["status"], "CONCLUÍDO")

    def test_two_interested_people_in_one_process_are_separate_rows(self):
        self.scan(
            [
                row(),
                row(interested="Outra Pessoa", interested_normalized="outra pessoa"),
            ]
        )

        self.assertEqual(len(self.store.list_processes()), 2)
        self.assertEqual(self.store.get_area_scan(self.store.latest_area_scan()["id"])["total"], 2)

    def test_rescan_does_not_duplicate_scan_items(self):
        self.scan([row()])
        self.scan([row()])

        latest = self.store.latest_area_scan()

        self.assertEqual(len(self.store.get_area_scan(latest["id"])["items"]), 1)
        self.assertEqual(len(self.store.list_processes()), 1)

    def test_latest_area_scan_is_the_most_recent(self):
        first = self.scan([row()])
        second = self.scan([row()])

        self.assertEqual(self.store.latest_area_scan()["id"], second)
        self.assertNotEqual(first, second)
        empty = Store.open(self.data / "outra.db")
        try:
            self.assertIsNone(empty.latest_area_scan())
        finally:
            empty.close()

    def test_scan_without_rows_is_recorded_as_empty(self):
        scan_id = self.scan([])

        scan = self.store.get_area_scan(scan_id)
        self.assertEqual(scan["total"], 0)
        self.assertEqual(scan["items"], [])

    def test_unknown_scan_returns_none(self):
        self.assertIsNone(self.store.get_area_scan(4242))


class AreaSummaryViewTests(AreaScanTestCase):
    def test_summary_is_empty_before_the_first_scan(self):
        payload = area_summary_payload(self.store)

        self.assertIsNone(payload["scan"])
        self.assertEqual(
            payload["counters"],
            {"total": 0, "pending": 0, "completed": 0, "ambiguous": 0, "blocked": 0, "not_found": 0},
        )

    def test_summary_reports_the_latest_scan_counters(self):
        self.scan([row()])
        self.scan(
            [
                row(),
                row(
                    process_key="102391/2026",
                    interested="Outra Pessoa",
                    interested_normalized="outra pessoa",
                    classification="ATO_COMPLEMENTADO",
                    needs_complement=False,
                ),
                row(
                    process_key="102392/2026",
                    interested="Terceira Pessoa",
                    interested_normalized="terceira pessoa",
                    classification="AMBIGUO",
                    needs_complement=False,
                ),
            ]
        )

        payload = area_summary_payload(self.store)

        self.assertEqual(
            payload["counters"],
            {"total": 3, "pending": 1, "completed": 1, "ambiguous": 1, "blocked": 0, "not_found": 0},
        )
        self.assertEqual(payload["scan"]["marker_label"], MARKER_LABEL)
        self.assertEqual(payload["scan"]["marker_value"], "6189")
        self.assertEqual(payload["scan"]["source_scope"], "sector_finalistic")
        self.assertEqual(payload["scan"]["origin"], "extension")
        self.assertTrue(payload["scan"]["observed_at"])


class ExtensionCommandTests(AreaScanTestCase):
    def test_extension_command_is_claimed_once(self):
        command_id = self.store.create_extension_command("SCAN_AREA", {})

        first = self.store.claim_extension_command("extension-test")
        second = self.store.claim_extension_command("extension-test")

        self.assertEqual(first["id"], command_id)
        self.assertEqual(first["type"], "SCAN_AREA")
        self.assertEqual(first["state"], "CLAIMED")
        self.assertEqual(first["client_id"], "extension-test")
        self.assertIsNone(second)

    def test_command_completion_stores_result(self):
        command_id = self.store.create_extension_command("SCAN_AREA", {"scope": "x"})
        self.store.claim_extension_command("extension-test")

        self.store.complete_extension_command(command_id, {"ok": True, "rows": []})

        command = self.store.get_extension_command(command_id)
        self.assertEqual(command["state"], "SUCCEEDED")
        self.assertEqual(command["result"], {"ok": True, "rows": []})
        self.assertIsNone(command["error"])
        self.assertIsNotNone(command["finished_at"])

    def test_command_failure_stores_error(self):
        command_id = self.store.create_extension_command("SCAN_AREA", {})
        self.store.claim_extension_command("extension-test")

        self.store.complete_extension_command(command_id, None, error="portal fechado")

        command = self.store.get_extension_command(command_id)
        self.assertEqual(command["state"], "FAILED")
        self.assertEqual(command["error"], "portal fechado")

    def test_payload_round_trips_as_json(self):
        command_id = self.store.create_extension_command(
            "SCAN_AREA", {"nested": {"list": [1, 2]}, "acento": "ação"}
        )

        self.assertEqual(
            self.store.get_extension_command(command_id)["payload"],
            {"nested": {"list": [1, 2]}, "acento": "ação"},
        )

    def test_two_clients_never_claim_the_same_command(self):
        total = 12
        for _ in range(total):
            self.store.create_extension_command("SCAN_AREA", {})
        claimed: list[int] = []
        lock = threading.Lock()

        def worker(client: str) -> None:
            while True:
                command = self.store.claim_extension_command(client)
                if command is None:
                    return
                with lock:
                    claimed.append(command["id"])

        threads = [threading.Thread(target=worker, args=(f"client-{index}",)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(sorted(claimed), list(range(1, total + 1)))
        self.assertEqual(len(claimed), len(set(claimed)))

    def test_oldest_queued_command_is_claimed_first(self):
        first = self.store.create_extension_command("STATUS", {})
        second = self.store.create_extension_command("SCAN_AREA", {})

        self.assertEqual(self.store.claim_extension_command("c")["id"], first)
        self.assertEqual(self.store.claim_extension_command("c")["id"], second)


class BridgeClientTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store.open(Path(self._tmp.name) / "atos-tce.db")
        self.addCleanup(self.store.close)

    def test_token_hash_round_trip(self):
        self.store.pair_bridge_client("extension-test", "a" * 64, origin="chrome-extension://abc")

        self.assertTrue(self.store.verify_bridge_token("extension-test", "a" * 64))
        self.assertFalse(self.store.verify_bridge_token("extension-test", "b" * 64))
        self.assertFalse(self.store.verify_bridge_token("outro-cliente", "a" * 64))

    def test_repairing_replaces_the_previous_token(self):
        self.store.pair_bridge_client("extension-test", "a" * 64)
        self.store.pair_bridge_client("extension-test", "c" * 64)

        self.assertFalse(self.store.verify_bridge_token("extension-test", "a" * 64))
        self.assertTrue(self.store.verify_bridge_token("extension-test", "c" * 64))
        self.assertEqual(len(self.store.list_bridge_clients()), 1)

    def test_unknown_client_is_rejected(self):
        self.assertFalse(self.store.verify_bridge_token("nao-existe", "a" * 64))

    def test_plaintext_token_is_never_stored(self):
        self.store.pair_bridge_client("extension-test", "a" * 64)

        row = self.store.list_bridge_clients()[0]
        self.assertEqual(row["token_hash"], "a" * 64)
        self.assertNotIn("token", {key for key in row if key != "token_hash"})


class SchemaV2MigrationTests(unittest.TestCase):
    def test_migration_from_v1_preserves_existing_rows(self):
        with TemporaryDirectory() as tmp:
            database = Path(tmp) / "atos-tce.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            for statement in SCHEMA_V1:
                connection.execute(statement)
            connection.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '1')")
            connection.execute(
                "INSERT INTO processes (process_key, interested, interested_normalized, status, created_at, updated_at) "
                "VALUES ('102390/2026', 'Pessoa Exemplo', 'pessoa exemplo', 'PENDENTE', "
                "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
            )
            connection.commit()
            connection.close()

            store = Store.open(database)
            try:
                # The v2 database must migrate forward, keeping every row.
                self.assertEqual(store.schema_version, SCHEMA_VERSION)
                processes = store.list_processes()
                self.assertEqual(len(processes), 1)
                self.assertEqual(processes[0]["process_key"], "102390/2026")
                self.assertEqual(processes[0]["needs_complement"], 0)
                self.assertIsNone(processes[0]["area_classification"])
            finally:
                store.close()

    def test_reopening_keeps_version_two(self):
        with TemporaryDirectory() as tmp:
            database = Path(tmp) / "atos-tce.db"
            store = Store.open(database)
            try:
                self.assertEqual(store.schema_version, SCHEMA_VERSION)
            finally:
                store.close()
            reopened = Store.open(database)
            try:
                self.assertEqual(reopened.schema_version, SCHEMA_VERSION)
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
