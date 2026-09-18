"""Tests for the Mesa fill-request state machine (M5 Task 1)."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.area_restrita.fill_service import FILL_STATES, FillError, FillService
from app.core.models import DocumentRecord, ProcessRecord
from app.core.store import SCHEMA_VERSION, Store

IDENTITY = {"processKey": "102390/2026", "interestedNormalized": "pessoa exemplo"}


class FillRequestTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.service = FillService(self.store)

    def make_process(self, *, status="PRONTO", process_key="102390/2026"):
        process_id = self.store.upsert_process(
            ProcessRecord(
                process_key=process_key,
                interested="Pessoa Exemplo",
                interested_normalized="pessoa exemplo",
                status=status,
            )
        )
        self.store.replace_documents(
            process_id,
            [
                DocumentRecord(
                    source_id=f"{process_key}|1|Ato",
                    title="Ato.pdf",
                    relative_path=f"archive/processos/{process_key.replace('/', '-')}/Ato.pdf",
                    sha256="a" * 64,
                    page_count=2,
                    event="1",
                )
            ],
        )
        return process_id


class FillStateMachineTests(FillRequestTestCase):
    def test_a_pronto_process_opens_and_then_reads_the_form(self):
        process_id = self.make_process()

        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.assertEqual(open_command["type"], "OPEN_ACT")
        self.assertEqual(open_command["payload"]["identity"]["processKey"], "102390/2026")
        self.assertEqual(self.store.get_fill_request(request_id)["state"], "OPENING")

        self.service.handle_command_result(open_command["id"], {"ok": True, "identity": IDENTITY})

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "READING")
        read_command = self.store.claim_extension_command("extension-test")
        self.assertEqual(read_command["type"], "READ_FORM")
        self.assertEqual(read_command["fill_request_id"], request_id)

    def test_the_request_records_which_command_it_is_waiting_for(self):
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)

        request = self.store.get_fill_request(request_id)
        command = self.store.get_extension_command(request["current_command_id"])

        self.assertEqual(command["type"], "OPEN_ACT")
        self.assertEqual(command["fill_request_id"], request_id)

    def test_a_process_that_is_not_pronto_is_refused(self):
        for status in ("PENDENTE", "REVISAR", "BAIXADO", "ERRO", "CONCLUÍDO"):
            with self.subTest(status=status):
                process_id = self.make_process(
                    status=status, process_key=f"10{abs(hash(status)) % 10000}/2026"
                )
                with self.assertRaises(FillError):
                    self.service.request_fill(process_id)

    def test_an_unknown_process_is_refused(self):
        with self.assertRaises(FillError):
            self.service.request_fill(4242)

    def test_an_identity_mismatch_blocks_the_request(self):
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.service.handle_command_result(
            open_command["id"],
            {"ok": True, "identity": {"processKey": "999999/2026", "interestedNormalized": "pessoa exemplo"}},
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "BLOQUEADO")
        self.assertIn("divergente", request["error"])
        self.assertIsNone(self.store.claim_extension_command("extension-test"))
        self.assertEqual(self.store.get_process(process_id)["status"], "BLOQUEADO")
        events = [event["event_type"] for event in self.store.get_process(process_id)["events"]]
        self.assertIn("fill_blocked", events)

    def test_a_missing_identity_blocks_the_request(self):
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.service.handle_command_result(open_command["id"], {"ok": True})

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "BLOQUEADO")

    def test_a_failed_open_result_moves_the_request_to_erro(self):
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.service.handle_command_result(
            open_command["id"], {"ok": False, "error": "ato não encontrado na lista"}
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "ERRO")
        self.assertIn("lista", request["error"])
        self.assertEqual(self.store.get_process(process_id)["status"], "ERRO")

    def test_a_stale_command_result_never_moves_the_request(self):
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")
        self.service.handle_command_result(open_command["id"], {"ok": True, "identity": IDENTITY})
        self.assertEqual(self.store.get_fill_request(request_id)["state"], "READING")

        # Replaying the OPEN_ACT result must not create a second READ_FORM.
        self.service.handle_command_result(open_command["id"], {"ok": True, "identity": IDENTITY})

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "READING")
        self.store.claim_extension_command("extension-test")
        self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_a_result_for_a_command_without_a_request_is_ignored(self):
        command_id = self.store.create_extension_command("SCAN_AREA", {})

        self.service.handle_command_result(command_id, {"ok": True})

        self.assertEqual(self.store.list_fill_requests(), [])

    def test_an_unknown_command_is_reported(self):
        with self.assertRaises(FillError):
            self.service.handle_command_result(4242, {"ok": True})

    def test_the_published_state_vocabulary_is_stable(self):
        self.assertEqual(
            FILL_STATES,
            ("OPENING", "READING", "PREFLIGHT", "FILLING", "PREENCHIDO", "BLOQUEADO", "ERRO"),
        )


class ManualFillRequestTests(FillRequestTestCase):
    def snapshot(self, process_key="102390/2026", interested="pessoa exemplo"):
        return {
            "identity": {"processKey": process_key, "interestedNormalized": interested},
            "generation": 3,
            "fields": {},
        }

    def test_a_manual_snapshot_matching_one_pronto_process_creates_a_request(self):
        process_id = self.make_process()

        request_id = self.service.request_manual_fill(self.snapshot())

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "PREFLIGHT")
        self.assertEqual(request["mode"], "manual")
        self.assertEqual(request["process_id"], process_id)
        self.assertEqual(request["form_snapshot"]["generation"], 3)

    def test_zero_matches_block(self):
        self.make_process()

        with self.assertRaises(FillError):
            self.service.request_manual_fill(self.snapshot(process_key="999999/2026"))

    def test_another_interested_person_does_not_match_the_same_process(self):
        self.make_process()
        self.store.upsert_process(
            ProcessRecord(
                process_key="102390/2026",
                interested="Outra Pessoa",
                interested_normalized="outra pessoa",
                status="REVISAR",
            )
        )

        # Two rows share the process key, so matching must use the person too.
        with self.assertRaises(FillError):
            self.service.request_manual_fill(self.snapshot(interested="outra pessoa"))

    def test_the_identity_is_matched_through_the_canonical_normalization(self):
        self.make_process()

        request_id = self.service.request_manual_fill(
            self.snapshot(interested="  PESSOA   Exemplo ")
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "PREFLIGHT")

    def test_a_snapshot_without_identity_blocks(self):
        with self.assertRaises(FillError):
            self.service.request_manual_fill({"generation": 1})

    def test_a_process_that_is_not_pronto_never_matches(self):
        self.make_process(status="REVISAR")

        with self.assertRaises(FillError):
            self.service.request_manual_fill(self.snapshot())


class SchemaV4Tests(FillRequestTestCase):
    def test_the_store_reports_schema_four(self):
        self.assertEqual(self.store.schema_version, SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, 4)

    def test_a_fill_request_round_trips_its_json_snapshot(self):
        process_id = self.make_process()
        request_id = self.store.create_fill_request(
            process_id, state="PREFLIGHT", mode="manual", form_snapshot={"generation": 7, "acento": "ção"}
        )

        request = self.store.get_fill_request(request_id)

        self.assertEqual(request["state"], "PREFLIGHT")
        self.assertEqual(request["form_snapshot"], {"generation": 7, "acento": "ção"})

    def test_updating_only_the_state_keeps_the_rest(self):
        process_id = self.make_process()
        request_id = self.store.create_fill_request(process_id, form_snapshot={"generation": 1})

        self.store.update_fill_request(request_id, state="READING")

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "READING")
        self.assertEqual(request["form_snapshot"], {"generation": 1})

    def test_listing_filters_by_process_and_state(self):
        first = self.make_process()
        second = self.make_process(process_key="102391/2026")
        self.store.create_fill_request(first, state="OPENING")
        self.store.create_fill_request(second, state="PREENCHIDO")

        self.assertEqual(len(self.store.list_fill_requests()), 2)
        self.assertEqual(len(self.store.list_fill_requests(process_id=first)), 1)
        self.assertEqual(len(self.store.list_fill_requests(state="PREENCHIDO")), 1)

    def test_an_unknown_fill_request_is_none(self):
        self.assertIsNone(self.store.get_fill_request(4242))


if __name__ == "__main__":
    unittest.main()
