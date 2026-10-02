"""Tests for the Mesa fill-request state machine (M5 Task 1)."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.area_restrita.fill_service import (
    FILL_STATES,
    FillError,
    FillService,
    ar1_run_id,
    sanitize_browser_diagnostics,
    summarize_field_results,
)
from app.area_restrita.reliability import ReliabilityRecorder
from app.area_restrita.preflight import FillBlocked, FillPlan, build_fill_plan
from app.analysis.legal import RULES_VERSION, selectable_legal_options
from app.core.models import DocumentRecord, FieldRecord, ProcessRecord
from app.core.store import SCHEMA_VERSION, Store

IDENTITY = {"processKey": "102390/2026", "interestedNormalized": "pessoa exemplo"}

#: A realistic OPEN_ACT outcome: the navigation reports the action and the
#: screen it acted on. The identity is optional at this stage (CR-01).
OPEN_RESULT = {
    "ok": True,
    "action": "open_act",
    "screen": "list",
    "waitingForFrame": True,
}


class FillRequestTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.capability_provider = CapabilityStateFixture(
            open_act="PRODUCTION",
            select_interested="PRODUCTION",
            next_process="PRODUCTION",
            return_to_list="PRODUCTION",
        )
        self.service = FillService(
            self.store,
            capability_provider=self.capability_provider,
        )

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


class CapabilityStateFixture:
    def __init__(self, **states):
        self.states = states

    def capabilities(self):
        return {name: {"state": state} for name, state in self.states.items()}


class FillStateMachineTests(FillRequestTestCase):
    def test_automatic_navigation_requires_production_capabilities_before_reserving(self):
        for states in (
            {"open_act": "UNQUALIFIED", "select_interested": "PRODUCTION"},
            {"open_act": "PRODUCTION", "select_interested": "EXPERIMENTAL"},
            {"open_act": "PRODUCTION", "select_interested": "QUALIFIED"},
            {"open_act": "PRODUCTION"},
        ):
            with self.subTest(states=states):
                process_id = self.make_process(process_key=f"10{len(self.store.list_fill_requests())}/2026")
                service = FillService(self.store, reliability=CapabilityStateFixture(**states))

                with self.assertRaises(FillError) as raised:
                    service.request_fill(process_id)

                self.assertIn("CAPABILITY_NOT_PRODUCTION", str(raised.exception))
                self.assertEqual(self.store.list_fill_requests(), [])
                self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_a_preenchido_process_can_start_another_fill_request(self):
        process_id = self.make_process(status="PREENCHIDO")

        request_id = self.service.request_fill(process_id)

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "OPENING")
        self.assertEqual(request["mode"], "automatic")

    def test_automatic_fill_uses_the_exact_portal_alias_from_the_latest_scan(self):
        process_id = self.make_process()
        self.store._connection.execute(
            "UPDATE processes SET interested = ?, interested_normalized = ?, portal_act_id = ? WHERE id = ?",
            ("Pessoa Exemplo Nome Completo", "pessoa exemplo nome completo", "act-fixture-42", process_id),
        )
        self.store.create_area_scan(
            source_scope="sector_finalistic",
            marker_label="FIXTURE - SANITIZADO",
            marker_value="fixture-marker",
            rows=[
                {
                    "process_key": "102390/2026",
                    "interested": "Pessoa Exemplo",
                    "interested_normalized": "pessoa exemplo",
                    "portal_act_id": "act-fixture-42",
                    "classification": "PRECISA_COMPLEMENTAR",
                }
            ],
        )

        request_id = self.service.request_fill(process_id)
        command = self.store.get_extension_command(
            self.store.get_fill_request(request_id)["current_command_id"]
        )

        self.assertEqual(
            command["payload"]["identity"],
            {
                "processKey": "102390/2026",
                "interestedNormalized": "pessoa exemplo",
                "portalActId": "act-fixture-42",
            },
        )
        self.assertEqual(
            command["payload"]["context"],
            {
                "scan_id": self.store.latest_area_scan()["id"],
                "source_scope": "sector_finalistic",
                "marker": {"label": "FIXTURE - SANITIZADO", "value": "fixture-marker"},
            },
        )

    def test_a_pronto_process_opens_and_then_reads_the_form(self):
        process_id = self.make_process()

        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.assertEqual(open_command["type"], "OPEN_ACT")
        self.assertEqual(open_command["payload"]["identity"]["processKey"], "102390/2026")
        self.assertEqual(self.store.get_fill_request(request_id)["state"], "OPENING")

        self.service.handle_command_result(open_command["id"], {**OPEN_RESULT, "identity": IDENTITY})

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
            {
                **OPEN_RESULT,
                "identity": {"processKey": "999999/2026", "interestedNormalized": "pessoa exemplo"},
            },
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "BLOQUEADO")
        self.assertIn("divergente", request["error"])
        self.assertIsNone(self.store.claim_extension_command("extension-test"))
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")
        events = [event["event_type"] for event in self.store.get_process(process_id)["events"]]
        self.assertIn("fill_blocked", events)

    def test_an_open_act_from_the_list_without_identity_advances_to_reading(self):
        # CR-01: OPEN_ACT only proves the navigation. The authoritative
        # identity arrives with READ_FORM, so a navigation outcome that carries
        # no identity must still move the request forward.
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.service.handle_command_result(
            open_command["id"],
            {"ok": True, "action": "open_act", "screen": "list", "waitingForFrame": True},
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "READING")
        read_command = self.store.claim_extension_command("extension-test")
        self.assertEqual(read_command["type"], "READ_FORM")
        self.assertEqual(read_command["fill_request_id"], request_id)

    def test_an_open_act_from_the_interested_screen_advances_to_reading(self):
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.service.handle_command_result(
            open_command["id"],
            {"ok": True, "action": "select_interested", "screen": "interested", "waitingForFrame": True},
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "READING")

    def test_an_open_act_already_on_the_form_advances_to_reading(self):
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.service.handle_command_result(
            open_command["id"],
            {"ok": True, "action": "already_open", "screen": "form", "waitingForFrame": False},
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "READING")

    def test_an_open_act_with_an_unknown_outcome_blocks(self):
        for payload in (
            {"ok": True},
            {"ok": True, "action": "open_act"},
            {"ok": True, "screen": "list"},
            {"ok": True, "action": "teleport", "screen": "list"},
            {"ok": True, "action": "open_act", "screen": "moon"},
        ):
            with self.subTest(payload=payload):
                process_id = self.make_process(
                    process_key=f"10{abs(hash(str(payload))) % 10000}/2026"
                )
                request_id = self.service.request_fill(process_id)
                open_command = self.store.claim_extension_command("extension-test")

                self.service.handle_command_result(open_command["id"], payload)

                request = self.store.get_fill_request(request_id)
                self.assertEqual(request["state"], "BLOQUEADO")
                self.assertIn("navegação", request["error"])
                self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_an_observed_identity_on_open_act_is_still_checked(self):
        # The form path may echo the identity it observed; when it does, a
        # divergence must block instead of being ignored.
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.service.handle_command_result(
            open_command["id"],
            {
                "ok": True,
                "action": "already_open",
                "screen": "form",
                "identity": {"processKey": "999999/2026", "interestedNormalized": "pessoa exemplo"},
            },
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "BLOQUEADO")
        self.assertIn("divergente", request["error"])

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
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")

    def test_an_ambiguous_page_blocks_instead_of_looking_like_a_portal_error(self):
        # CR-02: the extension refuses to pick between two matching frames.
        # That is a safety stop, not a transient portal failure.
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        self.service.handle_command_result(
            open_command["id"],
            {"ok": False, "code": "FORM_AMBIGUOUS", "error": "mais de uma moldura tem o formulário"},
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "BLOQUEADO")
        self.assertIn("moldura", request["error"])
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")
        events = [event["event_type"] for event in self.store.get_process(process_id)["events"]]
        self.assertIn("fill_blocked", events)

    def test_a_stale_command_result_never_moves_the_request(self):
        process_id = self.make_process()
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")
        self.service.handle_command_result(open_command["id"], {**OPEN_RESULT, "identity": IDENTITY})
        self.assertEqual(self.store.get_fill_request(request_id)["state"], "READING")

        # Replaying the OPEN_ACT result must not create a second READ_FORM.
        self.service.handle_command_result(open_command["id"], {**OPEN_RESULT, "identity": IDENTITY})

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
    def ready_process(self, *, status="PRONTO", process_key="102390/2026"):
        process_id = self.make_process(status=status, process_key=process_key)
        self.store.replace_fields(
            process_id,
            [
                FieldRecord(field_name=name, value=value, status="found", confidence=1.0)
                for name, value in MANDATORY_VALUES.items()
            ],
        )
        return process_id

    def snapshot(self, process_key="102390/2026", interested="pessoa exemplo", portal_act_id=None):
        return {
            "identity": {
                "processKey": process_key,
                "interestedNormalized": interested,
                **({"portalActId": portal_act_id} if portal_act_id is not None else {}),
            },
            "generation": 3,
            "documentNonce": "0123456789abcdef0123456789abcdef",
            "fields": form_controls(),
        }

    def test_a_manual_snapshot_matching_one_pronto_process_creates_a_request(self):
        process_id = self.ready_process()

        request_id = self.service.request_manual_fill(self.snapshot())

        request = self.store.get_fill_request(request_id)
        # The manual path runs the same backend preflight, so a matching form
        # with proposals goes straight to FILLING.
        self.assertEqual(request["state"], "FILLING")
        self.assertEqual(request["mode"], "manual")
        self.assertEqual(request["process_id"], process_id)
        # The preflight replaced the raw snapshot with the authorized plan.
        self.assertEqual(request["form_snapshot"]["plan"]["cargo"], "Professor")
        self.assertEqual(
            request["form_snapshot"]["modality_decision"]["option_value"], "VOLUNTARIA"
        )

    def test_manual_fill_resolves_a_scanned_name_alias_to_the_canonical_process(self):
        process_id = self.ready_process()
        self.store._connection.execute(
            "UPDATE processes SET interested = ?, interested_normalized = ? WHERE id = ?",
            ("Pessoa Exemplo Nome Completo", "pessoa exemplo nome completo", process_id),
        )
        self.store._connection.execute(
            "UPDATE processes SET portal_act_id = ? WHERE id = ?", ("act-fixture-42", process_id)
        )
        self.store.create_area_scan(
            source_scope="sector_finalistic",
            marker_label="FIXTURE - SANITIZADO",
            marker_value="fixture-marker",
            rows=[
                {
                    "process_key": "102390/2026",
                    "interested": "Pessoa Exemplo",
                    "interested_normalized": "pessoa exemplo",
                    "portal_act_id": "act-fixture-42",
                    "classification": "PRECISA_COMPLEMENTAR",
                }
            ],
        )

        request_id = self.service.request_manual_fill(
            self.snapshot(interested="pessoa exemplo")
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["process_id"], process_id)
        self.assertEqual(request["state"], "FILLING")
        self.assertEqual(len(self.store.list_processes()), 1)

    def test_manual_fill_accepts_a_preenchido_process(self):
        process_id = self.ready_process(status="PREENCHIDO")

        request_id = self.service.request_manual_fill(self.snapshot())

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["process_id"], process_id)
        self.assertEqual(request["state"], "FILLING")

    def test_manual_fill_is_not_gated_by_the_local_process_status(self):
        """Best-effort is authorized by the observed form, never by the status."""

        statuses = ("PENDENTE", "IDENTIFICADO", "BAIXADO", "REVISAR", "ERRO", "PREENCHIDO")
        for index, status in enumerate(statuses):
            with self.subTest(status=status):
                process_key = f"10239{index}/2026"
                process_id = self.ready_process(status=status, process_key=process_key)

                request_id = self.service.request_manual_fill(
                    self.snapshot(process_key=process_key)
                )

                request = self.store.get_fill_request(request_id)
                self.assertEqual(request["state"], "FILLING")
                self.assertEqual(request["process_id"], process_id)
                # A best-effort pass is not documentary completion: the local
                # status must survive the attempt untouched.
                self.assertEqual(self.store.get_process(process_id)["status"], status)

    def test_zero_matches_block(self):
        self.make_process()

        with self.assertRaises(FillError):
            self.service.request_manual_fill(self.snapshot(process_key="999999/2026"))

    def test_another_interested_person_does_not_match_the_same_process(self):
        first = self.make_process()
        second = self.store.upsert_process(
            ProcessRecord(
                process_key="102390/2026",
                interested="Outra Pessoa",
                interested_normalized="outra pessoa",
                status="REVISAR",
            )
        )
        self.store.replace_fields(
            second,
            [
                FieldRecord(field_name=name, value=value, status="found", confidence=1.0)
                for name, value in MANDATORY_VALUES.items()
            ],
        )

        # Two rows share the process key, so matching must use the person too.
        request_id = self.service.request_manual_fill(self.snapshot(interested="outra pessoa"))

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["process_id"], second)
        self.assertNotEqual(request["process_id"], first)

    def test_the_identity_is_matched_through_the_canonical_normalization(self):
        self.ready_process()

        request_id = self.service.request_manual_fill(
            self.snapshot(interested="  PESSOA   Exemplo ")
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "FILLING")

    def test_a_snapshot_without_identity_blocks(self):
        with self.assertRaises(FillError):
            self.service.request_manual_fill({"generation": 1})

    def test_the_observed_form_is_never_persisted_on_the_fill_request(self):
        """Only the authorized plan may reach SQLite, never the raw observation."""

        self.ready_process()
        snapshot = self.snapshot()
        snapshot["generation"] = 0  # an invalid generation fails inside the preflight

        request_id = self.service.request_manual_fill(snapshot)
        request = self.store.get_fill_request(request_id)

        self.assertEqual(request["state"], "ERRO")
        stored = request["form_snapshot"]
        self.assertNotIn("identity", stored)
        self.assertNotIn("fields", stored)
        self.assertNotIn("pessoa exemplo", json.dumps(stored))
        self.assertNotIn("102390", json.dumps(stored))

    def test_document_nonce_is_added_only_when_delivering_the_fill_command(self):
        self.ready_process()
        document_nonce = "0123456789abcdef0123456789abcdef"
        snapshot = self.snapshot()
        snapshot["documentNonce"] = document_nonce

        request_id = self.service.request_manual_fill(snapshot)
        request = self.store.get_fill_request(request_id)
        command = self.store.get_extension_command(request["current_command_id"])

        self.assertNotIn("document_nonce", command["payload"])
        self.assertNotIn(document_nonce, json.dumps(request["form_snapshot"]))
        delivered = self.service.command_for_extension(command)
        self.assertEqual(delivered["payload"]["document_nonce"], document_nonce)
        self.assertNotIn("document_nonce", self.store.get_extension_command(command["id"])["payload"])

    def test_a_manual_fill_without_a_document_nonce_queues_no_write(self):
        self.ready_process()
        snapshot = self.snapshot()
        snapshot.pop("documentNonce")

        request_id = self.service.request_manual_fill(snapshot)

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "BLOQUEADO")
        self.assertIn("document", request["error"])
        self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_a_successful_fill_must_echo_the_bound_document_nonce(self):
        process_id = self.ready_process()
        request_id = self.service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        fields = command["payload"]["fields"]
        result = {
            "ok": True,
            "identity": dict(IDENTITY),
            "generation_after": 4,
            "field_results": {
                name: {"before": "", "proposed": value, "after": value, "status": "changed"}
                for name, value in fields.items()
            },
        }

        self.service.handle_command_result(command["id"], result)

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "BLOQUEADO")
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")

class ManualSnapshotMixin:
    """Shared helpers for the manual-fill test classes."""

    def ready_process(self, *, values=None):
        process_id = self.make_process()
        self.store.replace_fields(
            process_id,
            [
                FieldRecord(field_name=name, value=value, status="found", confidence=1.0)
                for name, value in (MANDATORY_VALUES if values is None else values).items()
            ],
        )
        return process_id

    def snapshot(self, **overrides):
        controls = form_controls()
        controls["fundamento_legal"]["options"] = [
            {"value": "A", "label": MANDATORY_VALUES["fundamento_legal"]}
        ]
        for name, control in (overrides.pop("controls", {}) or {}).items():
            controls[name] = {**controls[name], **control}
        payload = {
            "identity": dict(IDENTITY),
            "generation": 3,
            "documentNonce": "0123456789abcdef0123456789abcdef",
            "fields": controls,
            "options": {},
        }
        payload.update(overrides)
        return payload


class ManualFallbackTests(ManualSnapshotMixin, FillRequestTestCase):
    """The operator-opened form must produce the same plan as the automatic path."""

    def test_the_manual_path_queues_the_same_fill_command_as_the_automatic_path(self):
        process_id = self.ready_process()
        service = FillService(self.store, capability_provider=self.capability_provider)

        manual_request = service.request_manual_fill(self.snapshot())
        manual_command = self.store.claim_extension_command("extension-test")

        automatic_request = service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(open_command["id"], {**OPEN_RESULT, "identity": IDENTITY})
        read_command = self.store.claim_extension_command("extension-test")
        # The extension always answers a command with an explicit ``ok``.
        service.handle_command_result(read_command["id"], {**self.snapshot(), "ok": True})
        automatic_command = self.store.claim_extension_command("extension-test")

        self.assertEqual(manual_command["type"], "FILL_FORM")
        self.assertEqual(automatic_command["type"], "FILL_FORM")
        self.assertEqual(manual_command["payload"], automatic_command["payload"])
        self.assertEqual(self.store.get_fill_request(manual_request)["state"], "FILLING")
        self.assertEqual(self.store.get_fill_request(automatic_request)["state"], "FILLING")
        self.assertEqual(self.store.get_fill_request(manual_request)["mode"], "manual")

    def test_the_manual_path_preserves_a_divergent_value_and_queues_other_fields(self):
        process_id = self.ready_process()
        service = FillService(self.store)

        request_id = service.request_manual_fill(
            self.snapshot(controls={"cargo": {"value": "Valor já existente", "options": []}})
        )

        request = self.store.get_fill_request(request_id)
        command = self.store.claim_extension_command("extension-test")
        self.assertEqual(request["state"], "FILLING")
        self.assertEqual(command["type"], "FILL_FORM")
        self.assertNotIn("cargo", command["payload"]["fields"])
        self.assertIn("matricula", command["payload"]["fields"])
        self.assertEqual(request["form_snapshot"]["preserved"]["cargo"], "Valor já existente")
        self.assertTrue(any("diverg" in warning.lower() for warning in request["form_snapshot"]["warnings"]))
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")

    def test_a_snapshot_without_controls_queues_an_empty_best_effort_plan(self):
        process_id = self.ready_process()
        service = FillService(self.store)

        request_id = service.request_manual_fill(
            {
                "identity": dict(IDENTITY),
                "generation": 3,
                "documentNonce": "0123456789abcdef0123456789abcdef",
            }
        )

        request = self.store.get_fill_request(request_id)
        command = self.store.claim_extension_command("extension-test")
        self.assertEqual(request["state"], "FILLING")
        self.assertEqual(command["type"], "FILL_FORM")
        self.assertEqual(command["payload"]["fields"], {})
        self.assertTrue(any("controle ausente" in warning for warning in request["form_snapshot"]["warnings"]))
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")


class FillResultSummaryTests(unittest.TestCase):
    def test_changed_and_equivalent_preserved_are_satisfied_but_divergence_is_not(self):
        summary = summarize_field_results(
            {
                "cargo": {"status": "changed", "before": "", "proposed": "Professor", "after": "Professor"},
                "matricula": {"status": "preserved", "before": "123", "proposed": "123", "after": "123"},
                "data_nascimento": {
                    "status": "preserved",
                    "before": "01/01/1950",
                    "proposed": "02/02/1950",
                    "after": "01/01/1950",
                    "warning": "existing_value_divergence",
                },
                "data_publicacao_doe": {"status": "disabled"},
            },
            mandatory_fields=("cargo", "matricula", "data_nascimento", "data_publicacao_doe"),
        )

        self.assertEqual(summary["changed"], ["cargo"])
        self.assertEqual(summary["preserved"], ["matricula", "data_nascimento"])
        self.assertFalse(summary["mandatory_satisfied"])
        self.assertEqual(
            {entry["field"] for entry in summary["unresolved"]},
            {"data_nascimento", "data_publicacao_doe"},
        )

    def test_optional_warning_does_not_make_mandatory_fields_unsatisfied(self):
        summary = summarize_field_results(
            {
                "cargo": {"status": "changed", "before": "", "proposed": "Professor", "after": "Professor"},
                "genero": {"status": "disabled", "warning": "control_disabled"},
            },
            mandatory_fields=("cargo",),
        )

        self.assertTrue(summary["mandatory_satisfied"])
        self.assertEqual(summary["unresolved"][0]["field"], "genero")


class FillServiceOutcomeTests(FillRequestTestCase):
    def ready_process(self, values=None, *, status="PRONTO"):
        process_id = self.make_process(status=status)
        values = dict(MANDATORY_VALUES if values is None else values)
        self.store.replace_fields(
            process_id,
            [
                FieldRecord(field_name=name, value=value, status="found", confidence=1.0)
                for name, value in values.items()
            ],
        )
        return process_id

    def reach_filling(self, *, values=None, controls=None):
        process_id = self.ready_process(values)
        request_id = self.service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")
        self.service.handle_command_result(open_command["id"], {**OPEN_RESULT, "identity": IDENTITY})
        read_command = self.store.claim_extension_command("extension-test")
        self.service.handle_command_result(
            read_command["id"],
            {
                "ok": True,
                "identity": IDENTITY,
                "generation": 3,
                "documentNonce": "0123456789abcdef0123456789abcdef",
                "fields": form_controls() if controls is None else controls,
            },
        )
        fill_command = self.store.claim_extension_command("extension-test")
        self.assertEqual(fill_command["type"], "FILL_FORM")
        return process_id, request_id, fill_command

    def reach_manual_filling(self, *, values=None, controls=None, status="PRONTO"):
        """The operator already opened the act, so no OPEN_ACT/READ_FORM happens."""

        process_id = self.ready_process(values, status=status)
        request_id = self.service.request_manual_fill(
            {
                "identity": dict(IDENTITY),
                "generation": 3,
                "documentNonce": "0123456789abcdef0123456789abcdef",
                "fields": form_controls() if controls is None else controls,
            }
        )
        fill_command = self.store.claim_extension_command("extension-test")
        self.assertEqual(fill_command["type"], "FILL_FORM")
        return process_id, request_id, fill_command

    @staticmethod
    def successful_fill_result(command):
        fields = command["payload"]["fields"]
        return {
            "ok": True,
            "identity": dict(IDENTITY),
            "generation_after": 4,
            "document_nonce": "0123456789abcdef0123456789abcdef",
            "field_results": {
                name: {"before": "", "proposed": value, "after": value, "status": "changed"}
                for name, value in fields.items()
            },
        }

    def test_a_partial_fill_finishes_the_request_but_keeps_the_process_pronto_and_retryable(self):
        process_id, request_id, fill_command = self.reach_filling(
            values={"cargo": "Professor", "matricula": "78.710-8/2"}
        )
        self.service.handle_command_result(
            fill_command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    "cargo": {"before": "", "proposed": "Professor", "after": "Professor", "status": "changed"},
                    "matricula": {
                        "before": "",
                        "proposed": "78.710-8/2",
                        "after": "",
                        "status": "disabled",
                        "warning": "control_disabled",
                    },
                },
            },
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "PREENCHIDO")
        self.assertEqual(request["form_snapshot"]["summary"]["changed"], ["cargo"])
        self.assertTrue(any(item["field"] == "matricula" for item in request["form_snapshot"]["summary"]["unresolved"]))
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")

        retry_id = self.service.request_fill(process_id)
        self.assertEqual(self.store.get_fill_request(retry_id)["state"], "OPENING")
        self.assertEqual(self.store.claim_extension_command("extension-test")["type"], "OPEN_ACT")

    def test_a_partial_manual_fill_in_revisar_never_launders_the_process_status(self):
        process_id, request_id, fill_command = self.reach_manual_filling(
            values={"cargo": "Professor", "matricula": "78.710-8/2"}, status="REVISAR"
        )

        self.service.handle_command_result(
            fill_command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    "cargo": {
                        "before": "",
                        "proposed": "Professor",
                        "after": "Professor",
                        "status": "changed",
                    },
                    "matricula": {
                        "before": "",
                        "proposed": "78.710-8/2",
                        "after": "",
                        "status": "disabled",
                        "warning": "control_disabled",
                    },
                },
            },
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "PREENCHIDO")
        summary = request["form_snapshot"]["summary"]
        self.assertFalse(summary["mandatory_satisfied"])
        self.assertFalse(summary["best_effort_satisfied"])
        # The attempt finished; the document did not become complete.
        self.assertEqual(self.store.get_process(process_id)["status"], "REVISAR")
        event_types = [
            event["event_type"] for event in self.store.list_workflow_events(process_id)
        ]
        self.assertIn("form_filled_partial", event_types)
        self.assertNotIn("form_filled", event_types)

    def test_a_fully_satisfied_mandatory_plan_marks_the_process_filled(self):
        process_id, request_id, fill_command = self.reach_filling()

        self.service.handle_command_result(
            fill_command["id"], self.successful_fill_result(fill_command)
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "PREENCHIDO")
        self.assertEqual(self.store.get_process(process_id)["status"], "PREENCHIDO")

    def test_a_placeholder_only_legal_catalog_is_reported_as_a_field_warning(self):
        controls = form_controls()
        controls["fundamento_legal"]["options"] = [
            {"value": "", "label": "Selecione"},
        ]
        process_id, request_id, fill_command = self.reach_filling(controls=controls)

        self.service.handle_command_result(
            fill_command["id"], self.successful_fill_result(fill_command)
        )

        request = self.store.get_fill_request(request_id)
        legal_result = request["form_snapshot"]["field_results"]["fundamento_legal"]
        self.assertEqual(legal_result["status"], "option_unavailable")
        self.assertEqual(legal_result["warning"], "option_unavailable")
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")

    def test_best_effort_contract_flows_from_read_through_plan_and_summary(self):
        controls = form_controls()
        controls["fundamento_legal"]["options"] = [
            {"value": "EC41", "label": "EC 41/2003"},
        ]
        controls["matricula"]["value"] = "matrícula divergente preenchida no portal"
        del controls["data_publicacao_doe"]
        process_id, request_id, fill_command = self.reach_filling(controls=controls)

        fields = fill_command["payload"]["fields"]
        self.assertNotEqual(MANDATORY_VALUES["fundamento_legal"], "EC 41/2003")
        self.assertEqual(fields["fundamento_legal"], "EC41")
        self.assertIn("cargo", fields)
        self.assertNotIn("data_publicacao_doe", fields)
        self.assertNotIn("matricula", fields)
        self.assertEqual(
            fill_command["payload"]["preserved"]["matricula"],
            "matrícula divergente preenchida no portal",
        )

        self.service.handle_command_result(
            fill_command["id"], self.successful_fill_result(fill_command)
        )

        request = self.store.get_fill_request(request_id)
        summary = request["form_snapshot"]["summary"]
        self.assertEqual(request["state"], "PREENCHIDO")
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")
        self.assertIn("fundamento_legal", summary["changed"])
        self.assertIn("cargo", summary["changed"])
        self.assertIn("matricula", summary["preserved"])
        self.assertTrue(
            {"data_publicacao_doe", "matricula"}.issubset(
                {entry["field"] for entry in summary["unresolved"]}
            )
        )
        for name in ("fundamento_legal", "cargo"):
            field_result = request["form_snapshot"]["field_results"][name]
            self.assertEqual(field_result["status"], "changed")
            self.assertEqual(field_result["after"], field_result["proposed"])

    def test_a_technical_failure_keeps_the_process_pronto_and_allows_retry(self):
        process_id, request_id, fill_command = self.reach_filling()

        self.service.handle_command_result(
            fill_command["id"], {"ok": False, "code": "FILL_FAILED", "error": "erro técnico"}
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "ERRO")
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")
        retry_id = self.service.request_fill(process_id)
        self.assertEqual(self.store.get_fill_request(retry_id)["state"], "OPENING")

    def test_a_fill_identity_mismatch_blocks_only_the_request_without_retrying(self):
        process_id, request_id, fill_command = self.reach_filling()

        self.service.handle_command_result(
            fill_command["id"],
            {"ok": False, "code": "IDENTITY_MISMATCH", "error": "identidade divergente"},
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "BLOQUEADO")
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")
        self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_a_stale_generation_retries_one_fresh_read_and_can_complete(self):
        process_id, request_id, fill_command = self.reach_filling()
        self.service.handle_command_result(
            fill_command["id"],
            {"ok": False, "code": "STALE_GENERATION", "generation_after": 4},
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "READING")
        self.assertEqual(request["form_snapshot"]["stale_generation_retries"], 1)
        read_command = self.store.claim_extension_command("extension-test")
        self.assertEqual(read_command["type"], "READ_FORM")
        self.service.handle_command_result(
            read_command["id"],
            {
                "ok": True,
                "identity": IDENTITY,
                "generation": 5,
                "documentNonce": "0123456789abcdef0123456789abcdef",
                "fields": form_controls(),
            },
        )
        retried_fill = self.store.claim_extension_command("extension-test")
        self.assertEqual(retried_fill["type"], "FILL_FORM")
        self.service.handle_command_result(
            retried_fill["id"], self.successful_fill_result(retried_fill)
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "PREENCHIDO")
        self.assertEqual(self.store.get_process(process_id)["status"], "PREENCHIDO")

    def test_a_second_stale_generation_ends_as_technical_error_without_status_corruption(self):
        process_id, request_id, fill_command = self.reach_filling()
        self.service.handle_command_result(
            fill_command["id"], {"ok": False, "code": "STALE_GENERATION", "generation_after": 4}
        )
        read_command = self.store.claim_extension_command("extension-test")
        self.service.handle_command_result(
            read_command["id"],
            {
                "ok": True,
                "identity": IDENTITY,
                "generation": 5,
                "documentNonce": "0123456789abcdef0123456789abcdef",
                "fields": form_controls(),
            },
        )
        retried_fill = self.store.claim_extension_command("extension-test")
        self.service.handle_command_result(
            retried_fill["id"], {"ok": False, "code": "STALE_GENERATION", "generation_after": 6}
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "ERRO")
        self.assertEqual(request["form_snapshot"]["stale_generation_retries"], 1)
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")
        self.assertIsNone(self.store.claim_extension_command("extension-test"))


class SchemaV4Tests(FillRequestTestCase):
    def test_the_store_reports_the_current_schema_version(self):
        # The single place that pins the current schema version for the whole
        # suite; a milestone that bumps it must update this assertion.
        self.assertEqual(self.store.schema_version, SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, 7)

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


MANDATORY_VALUES = {
    "modalidade": "aposentadoria voluntária",
    "fundamento_legal": "Art. 6º e art. 7º da Emenda Constitucional 41/2003",
    "data_publicacao_doe": "27/03/2024",
    "cargo": "Professor",
    "matricula": "78.710-8/2",
    "data_nascimento": "16/02/1950",
}


def process_payload(**overrides):
    values = dict(MANDATORY_VALUES)
    for name in overrides.pop("drop", ()):
        values.pop(name, None)
    values.update(overrides)
    return {
        "process_key": "102390/2026",
        "interested_normalized": "pessoa exemplo",
        "fields": [
            {"field_name": name, "value": value, "status": "found"}
            for name, value in values.items()
        ],
    }


def form_snapshot(**controls):
    fields = {
        name: {"value": "", "disabled": False, "readOnly": False, "options": []}
        for name in list(MANDATORY_VALUES) + ["genero"]
    }
    fields["modalidade"]["options"] = [
        {"value": "VOLUNTARIA", "label": "Aposentadoria voluntária"},
    ]
    fields["fundamento_legal"]["options"] = [
        {"value": "41", "label": "EC 41/2003"},
    ]
    fields.update(controls.pop("fields", {}))
    snapshot = {"identity": dict(IDENTITY), "generation": 3, "fields": fields}
    snapshot.update(controls)
    return snapshot


def form_controls(**overrides):
    """The seven mapped controls as the extension reports them."""

    controls = {
        name: {"value": "", "disabled": False, "readOnly": False, "options": []}
        for name in list(MANDATORY_VALUES) + ["genero"]
    }
    controls["modalidade"]["options"] = [
        {"value": "VOLUNTARIA", "label": "Aposentadoria voluntária"},
    ]
    controls["fundamento_legal"]["options"] = [
        {"value": "41", "label": "EC 41/2003"},
    ]
    for name, control in overrides.items():
        controls[name] = {**controls[name], **control}
    return controls


class PreflightTests(unittest.TestCase):
    def test_exact_identity_and_empty_controls_produce_a_plan(self):
        plan = build_fill_plan(process_payload(), form_snapshot())

        self.assertEqual(plan.generation, 3)
        self.assertEqual(plan.fields["cargo"], "Professor")
        self.assertEqual(plan.preserved, {})
        self.assertEqual(plan.legal_decision["rules_version"], RULES_VERSION)
        self.assertEqual(len(plan.fields), len(MANDATORY_VALUES))

    def test_a_missing_mandatory_proposal_warns_and_keeps_other_fields(self):
        plan = build_fill_plan(process_payload(drop=("data_nascimento",)), form_snapshot())

        self.assertNotIn("data_nascimento", plan.fields)
        self.assertIn("cargo", plan.fields)
        self.assertTrue(any("data_nascimento" in warning for warning in plan.warnings))

    def test_a_missing_optional_proposal_is_only_a_warning(self):
        plan = build_fill_plan(process_payload(), form_snapshot())

        self.assertNotIn("genero", plan.fields)
        self.assertTrue(any("genero" in warning for warning in plan.warnings))

    def test_an_existing_equal_value_is_preserved(self):
        snapshot = form_snapshot(fields={"cargo": {"value": "PROFESSOR", "options": []}})

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertEqual(plan.preserved, {"cargo": "PROFESSOR"})
        self.assertNotIn("cargo", plan.fields)

    def test_an_existing_divergent_value_is_preserved_and_other_fields_continue(self):
        snapshot = form_snapshot(fields={"cargo": {"value": "Valor já existente", "options": []}})

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertEqual(plan.preserved["cargo"], "Valor já existente")
        self.assertNotIn("cargo", plan.fields)
        self.assertIn("matricula", plan.fields)
        self.assertTrue(any("diverg" in warning.lower() for warning in plan.warnings))

    def test_legal_best_available_uses_a_real_option_even_without_literal_match(self):
        snapshot = form_snapshot(
            fields={
                "fundamento_legal": {
                    "value": "",
                    "options": [
                        {"value": "", "label": "Selecione o Fundamento Legal"},
                        {"value": "41", "label": "EC 41/2003"},
                        {"value": "47", "label": "EC 47/2005"},
                    ],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertEqual(plan.fields["fundamento_legal"], plan.legal_decision["option_value"])
        self.assertIn(
            plan.fields["fundamento_legal"],
            {option["value"] for option in selectable_legal_options(snapshot["fields"]["fundamento_legal"]["options"])},
        )
        self.assertEqual(plan.fields["fundamento_legal"], "41")

    def test_legal_best_available_skips_a_disabled_best_match(self):
        snapshot = form_snapshot(
            fields={
                "fundamento_legal": {
                    "value": "",
                    "options": [
                        {"value": "41", "label": "EC 41/2003", "disabled": True},
                        {"value": "47", "label": "EC 47/2005", "disabled": False},
                    ],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertEqual(plan.legal_decision["option_value"], "47")
        self.assertEqual(plan.fields["fundamento_legal"], "47")

    def test_an_ordinary_select_option_is_resolved_by_label_to_its_value(self):
        snapshot = form_snapshot(
            fields={
                "modalidade": {
                    "value": "",
                    "options": [{"value": "APOS", "label": "Aposentadoria voluntária"}],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertEqual(plan.fields["modalidade"], "APOS")

    def test_live_portal_modality_catalog_selects_the_best_real_option_and_reports_tie(self):
        fixture_path = (
            Path(__file__).parent
            / "fixtures"
            / "area-restrita"
            / "modalidade-catalog-supervisionado.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        snapshot = form_snapshot(
            fields={"modalidade": {"value": "", "options": fixture["options"]}}
        )

        plan = build_fill_plan(
            process_payload(modalidade=fixture["proposal"]), snapshot
        )

        self.assertEqual(plan.fields["modalidade"], "12")
        self.assertTrue(plan.modality_decision["automatic"])
        self.assertEqual(
            plan.modality_decision["option_label"], fixture["options"][4]["label"]
        )
        self.assertTrue(plan.modality_decision["tie_break_used"])
        self.assertEqual(plan.modality_decision["margin"], 0)
        self.assertTrue(
            any(
                "modalidade" in warning and "tie-broken-by-option-index" in warning
                for warning in plan.warnings
            )
        )

    def test_a_disabled_ordinary_select_option_is_reported_as_unavailable(self):
        snapshot = form_snapshot(
            fields={
                "modalidade": {
                    "value": "",
                    "options": [
                        {"value": "APOS", "label": "Aposentadoria voluntária", "disabled": True},
                    ],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertNotIn("modalidade", plan.fields)
        self.assertIn("cargo", plan.fields)
        self.assertTrue(any("modalidade" in warning and "opção" in warning.lower() for warning in plan.warnings))

    def test_an_unavailable_ordinary_select_warns_without_stopping_other_fields(self):
        snapshot = form_snapshot(
            fields={
                "modalidade": {
                    "value": "",
                    "options": [
                        {"value": "", "label": "Aposentadoria voluntária"},
                        {"value": "OUTRA", "label": "Outra modalidade"},
                    ],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertEqual(plan.fields["modalidade"], "OUTRA")
        self.assertTrue(plan.modality_decision["hard_conflict"])
        self.assertIn("cargo", plan.fields)
        self.assertTrue(
            any(
                "modalidade" in warning and "hard-conflict" in warning
                for warning in plan.warnings
            )
        )

    def test_a_readonly_mandatory_control_warns_and_other_fields_continue(self):
        snapshot = form_snapshot(fields={"cargo": {"value": "", "readOnly": True, "options": []}})

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertNotIn("cargo", plan.fields)
        self.assertIn("matricula", plan.fields)
        self.assertTrue(any("cargo" in warning and "desabilitado" in warning for warning in plan.warnings))

    def test_a_disabled_optional_control_is_only_a_warning(self):
        snapshot = form_snapshot(fields={"genero": {"value": "", "disabled": True, "options": []}})

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertNotIn("genero", plan.fields)
        self.assertTrue(any("desabilitado" in warning for warning in plan.warnings))

    def test_a_missing_mandatory_control_warns_and_other_fields_continue(self):
        snapshot = form_snapshot()
        del snapshot["fields"]["matricula"]

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertNotIn("matricula", plan.fields)
        self.assertIn("cargo", plan.fields)
        self.assertTrue(any("matricula" in warning and "ausente" in warning for warning in plan.warnings))

    def test_a_field_read_error_is_not_added_to_the_write_plan(self):
        snapshot = form_snapshot(fields={"cargo": {"readable": False}})

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertNotIn("cargo", plan.fields)
        self.assertIn("matricula", plan.fields)
        self.assertTrue(any("FIELD_READ_FAILED" in warning and "cargo" in warning for warning in plan.warnings))

    def test_a_stale_legal_resolver_value_is_skipped_and_warned(self):
        snapshot = form_snapshot(
            fields={
                "fundamento_legal": {
                    "value": "",
                    "options": [{"value": "41", "label": "EC 41/2003"}],
                }
            }
        )

        def stale_resolver(context, options):
            return {"automatic": True, "status": "selected", "option_value": "OLD", "method": "ranked"}

        plan = build_fill_plan(process_payload(), snapshot, legal_resolver=stale_resolver)

        self.assertNotIn("fundamento_legal", plan.fields)
        self.assertIn("cargo", plan.fields)
        self.assertTrue(any("catálogo" in warning.lower() for warning in plan.warnings))

    def test_a_placeholder_selection_is_empty_for_legal_best_available(self):
        snapshot = form_snapshot(
            fields={
                "fundamento_legal": {
                    "value": "-1",
                    "options": [
                        {"value": "-1", "label": "Selecione o Fundamento Legal"},
                        {"value": "41", "label": "EC 41/2003"},
                    ],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertNotIn("fundamento_legal", plan.preserved)
        self.assertEqual(plan.fields["fundamento_legal"], "41")

    def test_placeholder_only_legal_catalog_warns_and_keeps_other_fields(self):
        snapshot = form_snapshot(
            fields={
                "fundamento_legal": {
                    "value": "",
                    "options": [{"value": "", "label": "Selecione o Fundamento Legal"}],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertNotIn("fundamento_legal", plan.fields)
        self.assertIn("cargo", plan.fields)
        self.assertTrue(any("LEGAL_OPTIONS_EMPTY" in warning for warning in plan.warnings))

    def test_a_modality_placeholder_is_empty_before_matching_the_real_option(self):
        snapshot = form_snapshot(
            fields={
                "modalidade": {
                    "value": "-1",
                    "options": [
                        {"value": "-1", "label": "Selecione a modalidade"},
                        {"value": "VOLUNTARIA", "label": "Aposentadoria voluntária"},
                    ],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertNotIn("modalidade", plan.preserved)
        self.assertEqual(plan.fields["modalidade"], "VOLUNTARIA")

    def test_the_generation_is_required(self):
        for generation in (None, 0, -1, "3", 2.5):
            with self.subTest(generation=generation):
                snapshot = form_snapshot(generation=generation)
                with self.assertRaises(FillBlocked) as context:
                    build_fill_plan(process_payload(), snapshot)
                self.assertEqual(context.exception.code, "GENERATION_MISSING")

    def test_an_identity_mismatch_blocks(self):
        snapshot = form_snapshot(identity={"processKey": "999999/2026", "interestedNormalized": "pessoa exemplo"})

        with self.assertRaises(FillBlocked) as context:
            build_fill_plan(process_payload(), snapshot)

        self.assertEqual(context.exception.code, "IDENTITY_MISMATCH")

    def test_a_process_without_interested_identity_blocks(self):
        process = process_payload()
        process.pop("interested_normalized")

        with self.assertRaises(FillBlocked) as context:
            build_fill_plan(process, form_snapshot())

        self.assertEqual(context.exception.code, "IDENTITY_MISSING")

    def test_a_missing_identity_blocks(self):
        snapshot = form_snapshot()
        del snapshot["identity"]

        with self.assertRaises(FillBlocked) as context:
            build_fill_plan(process_payload(), snapshot)

        self.assertEqual(context.exception.code, "IDENTITY_MISSING")

    def test_an_automatic_legal_decision_replaces_the_proposal(self):
        snapshot = form_snapshot(
            fields={
                "fundamento_legal": {
                    "value": "",
                    "options": [
                        {"value": "A", "label": "Art. 6º e art. 7º da Emenda Constitucional 41/2003"},
                        {"value": "B", "label": "Art. 3º da Emenda Constitucional 47/2005"},
                    ],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot)

        self.assertTrue(plan.legal_decision["automatic"])
        self.assertEqual(plan.fields["fundamento_legal"], "A")

    def test_the_legal_engine_receives_the_current_form_options(self):
        seen = {}

        def resolver(context, options):
            seen["options"] = options
            seen["context"] = context
            return {"automatic": False, "status": "pending", "option_value": None}

        snapshot = form_snapshot(
            fields={
                "fundamento_legal": {
                    "value": "",
                    "options": [
                        {
                            "value": "41",
                            "label": "Art. 6º e art. 7º da Emenda Constitucional 41/2003",
                        }
                    ],
                }
            }
        )

        plan = build_fill_plan(process_payload(), snapshot, legal_resolver=resolver)

        self.assertEqual(seen["options"][0]["value"], "41")
        self.assertEqual(seen["context"]["cargo"], "Professor")
        self.assertIn("Emenda Constitucional 41", seen["context"]["operative_text"])
        self.assertNotIn("fundamento_legal", plan.fields)
        self.assertIn("cargo", plan.fields)
        self.assertTrue(any("sem decisão automática" in warning for warning in plan.warnings))

    def test_a_broken_legal_engine_degrades_to_a_warning(self):
        def resolver(context, options):
            raise RuntimeError("motor fora do ar")

        plan = build_fill_plan(process_payload(), form_snapshot(), legal_resolver=resolver)

        self.assertIsNone(plan.legal_decision)
        self.assertTrue(any("motor jurídico indisponível" in warning for warning in plan.warnings))


class StubPreflight:
    def __init__(self, plan=None, error=None):
        self.plan = plan
        self.error = error
        self.calls = []

    def __call__(self, process, snapshot):
        self.calls.append({"process": process["process_key"], "generation": snapshot.get("generation")})
        if self.error is not None:
            raise self.error
        return self.plan


class FillServicePreflightTests(FillRequestTestCase):
    def reach_reading(self, stub):
        process_id = self.make_process()
        service = FillService(
            self.store, preflight=stub, capability_provider=self.capability_provider
        )
        request_id = service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            open_command["id"], {"ok": True, "action": "open_act", "screen": "list"}
        )
        read_command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            read_command["id"],
            {
                "ok": True,
                "identity": IDENTITY,
                "generation": 4,
                "documentNonce": "0123456789abcdef0123456789abcdef",
            },
        )
        return service, request_id

    def test_a_read_form_with_a_wrong_identity_blocks_before_the_preflight(self):
        stub = StubPreflight(error=AssertionError("o preflight não pode rodar com identidade errada"))
        process_id = self.make_process()
        service = FillService(
            self.store, preflight=stub, capability_provider=self.capability_provider
        )
        request_id = service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            open_command["id"], {"ok": True, "action": "open_act", "screen": "list"}
        )
        read_command = self.store.claim_extension_command("extension-test")

        service.handle_command_result(
            read_command["id"],
            {
                "ok": True,
                "identity": {"processKey": "999999/2026", "interestedNormalized": "pessoa exemplo"},
                "generation": 4,
            },
        )

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "BLOQUEADO")
        self.assertIn("divergente", request["error"])
        self.assertEqual(stub.calls, [])
        self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_no_write_is_authorized_before_a_validated_read_form(self):
        # CR-01: between OPEN_ACT and a validated READ_FORM the only queued
        # command may be the read itself.
        stub = StubPreflight(
            plan=FillPlan(identity=dict(IDENTITY), generation=4, fields={"cargo": "Professor"})
        )
        process_id = self.make_process()
        service = FillService(
            self.store, preflight=stub, capability_provider=self.capability_provider
        )
        service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")

        service.handle_command_result(
            open_command["id"], {"ok": True, "action": "open_act", "screen": "list"}
        )

        queued = self.store.claim_extension_command("extension-test")
        self.assertEqual(queued["type"], "READ_FORM")
        self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_a_successful_read_runs_the_preflight_and_queues_fill_form(self):
        plan = FillPlan(
            identity=dict(IDENTITY), generation=4, fields={"cargo": "Professor"}, preserved={"matricula": "1"}
        )
        stub = StubPreflight(plan=plan)

        _service, request_id = self.reach_reading(stub)

        self.assertEqual(stub.calls, [{"process": "102390/2026", "generation": 4}])
        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "FILLING")
        command = self.store.claim_extension_command("extension-test")
        self.assertEqual(command["type"], "FILL_FORM")
        self.assertEqual(command["payload"]["fields"], {"cargo": "Professor"})
        self.assertEqual(command["payload"]["generation"], 4)

    def test_a_blocked_preflight_never_queues_a_fill_command(self):
        stub = StubPreflight(error=FillBlocked("EXISTING_VALUE_DIVERGENCE", ["matricula"]))

        _service, request_id = self.reach_reading(stub)

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "ERRO")
        self.assertIn("EXISTING_VALUE_DIVERGENCE", request["error"])
        self.assertIn("matricula", request["error"])
        self.assertEqual(self.store.get_process(request["process_id"])["status"], "PRONTO")
        self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_a_broken_preflight_moves_the_request_to_erro(self):
        stub = StubPreflight(error=RuntimeError("inesperado"))

        _service, request_id = self.reach_reading(stub)

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "ERRO")
        self.assertIn("preflight falhou", request["error"])
        self.assertNotIn("documentNonce", json.dumps(request["form_snapshot"]))


AR1_BUILD = "task3-build"


def _preflight_that_fails(process, snapshot):
    raise RuntimeError("preflight fixture failure")


class Ar1ManualFillReliabilityTests(ManualSnapshotMixin, FillRequestTestCase):
    """AR-1 must be navigation-independent and must emit sanitized telemetry."""

    def ar1_service(self):
        self.recorder = ReliabilityRecorder(self.data, AR1_BUILD)
        return FillService(
            self.store, reliability=self.recorder, reliability_environment="offline"
        )

    def events(self):
        path = self.data / "reliability" / "events.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def boundaries(self, request_id):
        run_id = ar1_run_id(request_id)
        return [
            event["boundary"]
            for event in self.events()
            if event.get("type") == "transition" and event.get("run_id") == run_id
        ]

    def finishes(self):
        return [event for event in self.events() if event.get("type") == "run_finished"]

    def test_manual_fill_never_queues_open_act_or_open_next_act(self):
        self.ready_process()
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())

        types = [
            row[0]
            for row in self.store._connection.execute(
                "SELECT command_type FROM extension_commands ORDER BY id"
            )
        ]
        self.assertEqual(types, ["FILL_FORM"])
        self.assertNotIn("OPEN_ACT", types)
        self.assertNotIn("OPEN_NEXT_ACT", types)
        self.assertEqual(self.store.get_fill_request(request_id)["state"], "FILLING")

    def test_manual_fill_rejects_identity_change_before_write(self):
        process_id = self.ready_process()
        service = self.ar1_service()
        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")

        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": {"processKey": "outro/2026", "interestedNormalized": "outra pessoa"},
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {},
            },
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "BLOQUEADO")
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["passed"])

    def test_manual_fill_records_form_not_available_as_ar1_failure(self):
        self.ready_process()
        service = self.ar1_service()
        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")

        service.handle_command_result(
            command["id"],
            {"ok": False, "code": "FORM_NOT_AVAILABLE", "error": "sem formulário"},
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "ERRO")
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["passed"])
        self.assertEqual(finished[0]["result_code"], "FORM_NOT_AVAILABLE")

    def test_manual_fill_records_the_ar1_boundary_sequence(self):
        process_id = self.ready_process()
        service = self.ar1_service()
        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")

        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    name: {"before": "", "proposed": value, "after": value, "status": "changed"}
                    for name, value in command["payload"]["fields"].items()
                },
            },
        )

        self.assertEqual(
            self.boundaries(request_id),
            [
                "current_form_detected",
                "manual_fill_requested",
                "preflight_completed",
                "fill_command_completed",
                "reread_completed",
            ],
        )
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0]["passed"])
        self.assertEqual(self.store.get_process(process_id)["status"], "PREENCHIDO")
        run_id = ar1_run_id(request_id)
        ordered = [event["type"] for event in self.events() if event.get("run_id") == run_id]
        self.assertEqual(
            ordered,
            [
                "run_start",
                "transition",
                "transition",
                "transition",
                "transition",
                "transition",
                "run_finished",
            ],
        )
        raw = (self.data / "reliability" / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("102390/2026", raw)
        self.assertNotIn("pessoa exemplo", raw)

    def test_ar1_never_persists_a_raw_route_or_identity_in_diagnostics(self):
        self.ready_process()
        service = self.ar1_service()

        request_id = service.request_manual_fill(
            self.snapshot(
                diagnostics={
                    "browser_session_id": "3f1c9b2e-0a44-4d5a-9c11-8b7f2e6a1d33",
                    "tab_ref": "tab-1",
                    "frame_ref": "frame-0",
                    "route": "/SISTEMAS/PROCESSO/ComplementarAto.asp?processo=102390&doc=9",
                    "screen": "form",
                    "generation": 3,
                    "cpf": "000.000.000-00",
                }
            )
        )

        request = self.store.get_fill_request(request_id)
        diagnostics = request["form_snapshot"]["diagnostics"]
        self.assertEqual(
            sorted(diagnostics),
            ["browser_session_id", "frame_ref", "generation", "route", "screen", "tab_ref"],
        )
        self.assertEqual(diagnostics["route"], "/SISTEMAS/PROCESSO/ComplementarAto.asp")
        raw = json.dumps(request)
        self.assertNotIn("processo=", raw)
        self.assertNotIn("cpf", raw.lower())

    def test_marking_ar1_experimental_records_the_build_and_never_qualifies(self):
        recorder = ReliabilityRecorder(self.data, AR1_BUILD)

        recorder.mark_experimental(
            "manual_form_fill", reason=f"contrato offline AR-1 verde em {AR1_BUILD}"
        )

        capability = recorder.capabilities()["manual_form_fill"]
        self.assertEqual(capability["state"], "EXPERIMENTAL")
        self.assertIn(AR1_BUILD, capability["reason"])
        self.assertFalse(recorder.evaluate("manual_form_fill", "real-dev")["qualified"])
        self.assertFalse(recorder.evaluate("manual_form_fill", "offline")["qualified"])

    def test_a_failed_preflight_never_persists_raw_diagnostics(self):
        self.ready_process()
        recorder = ReliabilityRecorder(self.data, AR1_BUILD)
        service = FillService(
            self.store,
            preflight=_preflight_that_fails,
            reliability=recorder,
            reliability_environment="offline",
        )

        request_id = service.request_manual_fill(
            self.snapshot(
                diagnostics={
                    "browser_session_id": "3f1c9b2e-0a44-4d5a-9c11-8b7f2e6a1d33",
                    "tab_ref": "tab-1",
                    "route": "https://portal.tce.rn.gov.br/SISTEMAS/ato.asp?processo=102390",
                    "screen": "form",
                    "cpf": "000.000.000-00",
                }
            )
        )

        request = self.store.get_fill_request(request_id)
        raw = json.dumps(request)
        self.assertEqual(request["state"], "ERRO")
        self.assertNotIn("processo=", raw)
        self.assertNotIn("https://", raw)
        self.assertNotIn("cpf", raw.lower())
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["passed"])

    def test_the_diagnostics_sanitizer_rejects_urls_unknown_screens_and_bad_refs(self):
        self.assertIsNone(
            sanitize_browser_diagnostics(
                {
                    "route": "https://host/path?x=1",
                    "screen": "banana",
                    "tab_ref": "tab 1 / x",
                }
            )
        )
        self.assertEqual(
            sanitize_browser_diagnostics(
                {"route": "/A/B.asp", "screen": "FORM", "tab_ref": "tab-1"}
            ),
            {"route": "/A/B.asp", "screen": "form", "tab_ref": "tab-1"},
        )

    def test_a_restarted_service_fails_closed_when_transient_document_nonce_is_lost(self):
        self.ready_process()
        recorder = ReliabilityRecorder(self.data, AR1_BUILD)
        first = FillService(self.store, reliability=recorder, reliability_environment="offline")
        request_id = first.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")

        restarted = FillService(self.store, reliability=recorder, reliability_environment="offline")
        restarted.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    name: {"before": "", "proposed": value, "after": value, "status": "changed"}
                    for name, value in command["payload"]["fields"].items()
                },
            },
        )

        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["passed"])
        self.assertEqual(finished[0]["result_code"], "STALE_FORM")
        self.assertEqual(finished[0]["run_id"], ar1_run_id(request_id))
        self.assertEqual(self.store.get_fill_request(request_id)["state"], "BLOQUEADO")

    def test_a_refused_manual_attempt_is_recorded_as_a_failed_run(self):
        self.ready_process()
        service = self.ar1_service()

        unknown = self.snapshot()
        unknown["identity"] = {**unknown["identity"], "processKey": "999999/2026"}
        with self.assertRaises(FillError):
            service.request_manual_fill(unknown)

        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["passed"])
        self.assertEqual(finished[0]["result_code"], "PROCESS_NOT_FOUND")
        self.assertTrue(finished[0]["run_id"].startswith("manual-fill-attempt:"))

    def test_a_best_effort_run_passes_when_mandatory_fields_have_no_proposal(self):
        """A run passes on what it authorized, not on what the document lacks."""

        process_id = self.ready_process(values={"cargo": "Professor"})
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        self.assertEqual(command["type"], "FILL_FORM")
        self.assertEqual(sorted(command["payload"]["fields"]), ["cargo"])

        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    "cargo": {
                        "before": "",
                        "proposed": "Professor",
                        "after": "Professor",
                        "status": "changed",
                    }
                },
            },
        )

        summary = self.store.get_fill_request(request_id)["form_snapshot"]["summary"]
        self.assertFalse(summary["mandatory_satisfied"])
        self.assertTrue(summary["best_effort_satisfied"])
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0]["passed"])
        self.assertEqual(finished[0]["result_code"], "BEST_EFFORT_OK")
        # Best-effort success is not documentary completion.
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")

    def test_a_disabled_planned_field_keeps_the_run_failing(self):
        self.ready_process(values={"cargo": "Professor"})
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    "cargo": {
                        "before": "",
                        "proposed": "Professor",
                        "after": "",
                        "status": "disabled",
                        "warning": "control_disabled",
                    }
                },
            },
        )

        summary = self.store.get_fill_request(request_id)["form_snapshot"]["summary"]
        self.assertFalse(summary["best_effort_satisfied"])
        finished = self.finishes()
        self.assertFalse(finished[-1]["passed"])
        self.assertEqual(finished[-1]["result_code"], "BEST_EFFORT_FAILED")

    def test_a_planned_field_diverging_from_the_proposal_keeps_the_run_failing(self):
        self.ready_process(values={"cargo": "Professor"})
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    "cargo": {
                        "before": "",
                        "proposed": "Professor",
                        "after": "Outro cargo",
                        "status": "changed",
                    }
                },
            },
        )

        summary = self.store.get_fill_request(request_id)["form_snapshot"]["summary"]
        self.assertFalse(summary["best_effort_satisfied"])
        self.assertFalse(self.finishes()[-1]["passed"])

    def test_a_planned_field_missing_from_the_results_keeps_the_run_failing(self):
        self.ready_process(values={"cargo": "Professor"})
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {},
            },
        )

        summary = self.store.get_fill_request(request_id)["form_snapshot"]["summary"]
        self.assertFalse(summary["best_effort_satisfied"])
        self.assertFalse(self.finishes()[-1]["passed"])

    def test_an_empty_plan_succeeds_as_best_effort_without_inventing_values(self):
        process_id = self.ready_process(values={})
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        self.assertEqual(command["type"], "FILL_FORM")
        # Nothing was authorized, so nothing may be written.
        self.assertEqual(command["payload"]["fields"], {})

        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {},
            },
        )

        summary = self.store.get_fill_request(request_id)["form_snapshot"]["summary"]
        self.assertFalse(summary["mandatory_satisfied"])
        self.assertTrue(summary["best_effort_satisfied"])
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0]["passed"])
        self.assertEqual(finished[0]["result_code"], "BEST_EFFORT_OK")
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")

    def test_an_ambiguous_form_keeps_the_run_failing_before_any_write(self):
        process_id = self.ready_process()
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            command["id"], {"ok": False, "code": "FORM_AMBIGUOUS"}
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "BLOQUEADO")
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["passed"])
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")

    def test_a_proposal_that_does_not_match_the_plan_keeps_the_run_failing(self):
        """The extension must write the value the backend authorized, not one of its own."""

        self.ready_process(values={"cargo": "Professor"})
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        self.assertEqual(command["payload"]["fields"], {"cargo": "Professor"})

        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    "cargo": {
                        "before": "",
                        "proposed": "Outro cargo",
                        "after": "Outro cargo",
                        "status": "changed",
                    }
                },
            },
        )

        summary = self.store.get_fill_request(request_id)["form_snapshot"]["summary"]
        self.assertFalse(summary["best_effort_satisfied"])
        finished = self.finishes()
        self.assertFalse(finished[-1]["passed"])
        self.assertEqual(finished[-1]["result_code"], "BEST_EFFORT_FAILED")

    def test_an_exhausted_stale_generation_keeps_the_run_failing(self):
        self.ready_process()
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        fill_command = self.store.claim_extension_command("extension-test")
        self.assertEqual(fill_command["type"], "FILL_FORM")
        service.handle_command_result(
            fill_command["id"],
            {"ok": False, "code": "STALE_GENERATION", "generation_after": 4},
        )

        read_command = self.store.claim_extension_command("extension-test")
        self.assertEqual(read_command["type"], "READ_FORM")
        service.handle_command_result(
            read_command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation": 5,
                "documentNonce": "0123456789abcdef0123456789abcdef",
                "fields": form_controls(),
            },
        )

        retried_fill = self.store.claim_extension_command("extension-test")
        self.assertEqual(retried_fill["type"], "FILL_FORM")
        service.handle_command_result(
            retried_fill["id"],
            {"ok": False, "code": "STALE_GENERATION", "generation_after": 6},
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "ERRO")
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["passed"])

    def test_a_form_that_changes_to_another_process_blocks_without_touching_it(self):
        """Review Focus #2: the act moved to B while A was being written."""

        first = self.ready_process(values={"cargo": "Professor"})
        second = self.make_process(status="PRONTO", process_key="200000/2026")
        service = self.ar1_service()

        request_id = service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": {"processKey": "200000/2026", "interestedNormalized": "pessoa exemplo"},
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    "cargo": {
                        "before": "",
                        "proposed": "Professor",
                        "after": "Professor",
                        "status": "changed",
                    }
                },
            },
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "BLOQUEADO")
        finished = self.finishes()
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["passed"])
        # Neither act was promoted: the write never belonged to B.
        self.assertEqual(self.store.get_process(first)["status"], "PRONTO")
        self.assertEqual(self.store.get_process(second)["status"], "PRONTO")

    def test_an_exceptional_process_with_no_useful_field_still_passes_best_effort(self):
        """Review Focus #5: ERRO/REVISAR without proposals is a pendency, not a failure."""

        for index, status in enumerate(("ERRO", "REVISAR")):
            with self.subTest(status=status):
                process_key = f"30000{index}/2026"
                process_id = self.make_process(status=status, process_key=process_key)
                service = self.ar1_service()

                request_id = service.request_manual_fill(
                    self.snapshot(identity={**IDENTITY, "processKey": process_key})
                )
                command = self.store.claim_extension_command("extension-test")
                self.assertEqual(command["type"], "FILL_FORM")
                # Nothing was found, so nothing may be written.
                self.assertEqual(command["payload"]["fields"], {})
                service.handle_command_result(
                    command["id"],
                    {
                        "ok": True,
                        "identity": {**IDENTITY, "processKey": process_key},
                        "generation_after": 4,
                        "document_nonce": "0123456789abcdef0123456789abcdef",
                        "field_results": {},
                    },
                )

                summary = self.store.get_fill_request(request_id)["form_snapshot"]["summary"]
                self.assertFalse(summary["mandatory_satisfied"])
                self.assertTrue(summary["best_effort_satisfied"])
                self.assertTrue(self.finishes()[-1]["passed"])
                # The attempt never rewrites the incomplete local status.
                self.assertEqual(self.store.get_process(process_id)["status"], status)

    def run_successful_fill(self, service):
        """One complete AR-1 trial: read the opened form, fill it, reread it."""

        service.request_manual_fill(self.snapshot())
        command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            command["id"],
            {
                "ok": True,
                "identity": dict(IDENTITY),
                "generation_after": 4,
                "document_nonce": "0123456789abcdef0123456789abcdef",
                "field_results": {
                    name: {"before": "", "proposed": value, "after": value, "status": "changed"}
                    for name, value in command["payload"]["fields"].items()
                },
            },
        )

    def test_a_refused_attempt_resets_a_nineteen_pass_streak(self):
        self.ready_process()
        service = self.ar1_service()
        for _ in range(19):
            self.run_successful_fill(service)
        self.assertEqual(self.recorder.evaluate("manual_form_fill", "offline")["streak"], 19)

        unknown = self.snapshot()
        unknown["identity"] = {**unknown["identity"], "processKey": "999999/2026"}
        with self.assertRaises(FillError):
            service.request_manual_fill(unknown)

        self.assertEqual(self.recorder.evaluate("manual_form_fill", "offline")["streak"], 0)

    def test_a_reported_attempt_failure_is_recorded_and_resets_the_streak(self):
        self.ready_process()
        service = self.ar1_service()
        for _ in range(19):
            self.run_successful_fill(service)
        self.assertEqual(self.recorder.evaluate("manual_form_fill", "offline")["streak"], 19)

        service.record_manual_attempt_failure("FORM_AMBIGUOUS")

        self.assertEqual(self.recorder.evaluate("manual_form_fill", "offline")["streak"], 0)
        finished = self.finishes()
        self.assertFalse(finished[-1]["passed"])
        self.assertEqual(finished[-1]["result_code"], "FORM_AMBIGUOUS")
        self.assertTrue(finished[-1]["run_id"].startswith("manual-fill-attempt:"))

    def test_an_unknown_attempt_code_is_refused(self):
        self.ready_process()
        service = self.ar1_service()

        with self.assertRaises(FillError):
            service.record_manual_attempt_failure("PESSOA EXEMPLO")

        self.assertEqual(self.finishes(), [])

    def test_a_reported_detection_failure_does_not_claim_a_detected_form(self):
        self.ready_process()
        service = self.ar1_service()

        service.record_manual_attempt_failure("FORM_NOT_AVAILABLE")

        run_id = self.finishes()[0]["run_id"]
        transitions = [
            event
            for event in self.events()
            if event.get("run_id") == run_id and event.get("type") == "transition"
        ]
        self.assertEqual(transitions[0]["boundary"], "current_form_attempted")
        self.assertEqual(transitions[0]["result_code"], "FORM_NOT_DETECTED")
        self.assertEqual(transitions[0]["state_after"], "UNKNOWN")

    def test_a_detected_form_refusal_still_records_the_detection(self):
        self.ready_process()
        service = self.ar1_service()

        unknown = self.snapshot()
        unknown["identity"] = {**unknown["identity"], "processKey": "999999/2026"}
        with self.assertRaises(FillError):
            service.request_manual_fill(unknown)

        run_id = self.finishes()[0]["run_id"]
        transitions = [
            event
            for event in self.events()
            if event.get("run_id") == run_id and event.get("type") == "transition"
        ]
        self.assertEqual(transitions[0]["boundary"], "current_form_detected")
        self.assertEqual(transitions[0]["result_code"], "FORM_DETECTED")




if __name__ == "__main__":
    unittest.main()
