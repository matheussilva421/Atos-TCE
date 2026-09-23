"""Tests for the Mesa fill-request state machine (M5 Task 1)."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.area_restrita.fill_service import FILL_STATES, FillError, FillService
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
        self.assertEqual(self.store.get_process(process_id)["status"], "BLOQUEADO")
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
        self.assertEqual(self.store.get_process(process_id)["status"], "ERRO")

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
        self.assertEqual(self.store.get_process(process_id)["status"], "BLOQUEADO")
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
    def ready_process(self, *, status="PRONTO"):
        process_id = self.make_process(status=status)
        self.store.replace_fields(
            process_id,
            [
                FieldRecord(field_name=name, value=value, status="found", confidence=1.0)
                for name, value in MANDATORY_VALUES.items()
            ],
        )
        return process_id

    def snapshot(self, process_key="102390/2026", interested="pessoa exemplo"):
        return {
            "identity": {"processKey": process_key, "interestedNormalized": interested},
            "generation": 3,
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
        self.ready_process()

        request_id = self.service.request_manual_fill(
            self.snapshot(interested="  PESSOA   Exemplo ")
        )

        self.assertEqual(self.store.get_fill_request(request_id)["state"], "FILLING")

    def test_a_snapshot_without_identity_blocks(self):
        with self.assertRaises(FillError):
            self.service.request_manual_fill({"generation": 1})

    def test_a_process_that_is_not_pronto_never_matches(self):
        self.ready_process(status="REVISAR")

        with self.assertRaises(FillError):
            self.service.request_manual_fill(self.snapshot())


class ManualFallbackTests(FillRequestTestCase):
    """The operator-opened form must produce the same plan as the automatic path."""

    def ready_process(self, *, values=None):
        process_id = self.make_process()
        self.store.replace_fields(
            process_id,
            [
                FieldRecord(field_name=name, value=value, status="found", confidence=1.0)
                for name, value in (values or MANDATORY_VALUES).items()
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
            "fields": controls,
            "options": {},
        }
        payload.update(overrides)
        return payload

    def test_the_manual_path_queues_the_same_fill_command_as_the_automatic_path(self):
        process_id = self.ready_process()
        service = FillService(self.store)

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

        request_id = service.request_manual_fill({"identity": dict(IDENTITY), "generation": 3})

        request = self.store.get_fill_request(request_id)
        command = self.store.claim_extension_command("extension-test")
        self.assertEqual(request["state"], "FILLING")
        self.assertEqual(command["type"], "FILL_FORM")
        self.assertEqual(command["payload"]["fields"], {})
        self.assertTrue(any("controle ausente" in warning for warning in request["form_snapshot"]["warnings"]))
        self.assertEqual(self.store.get_process(process_id)["status"], "PRONTO")


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

        self.assertNotIn("modalidade", plan.fields)
        self.assertIn("cargo", plan.fields)
        self.assertTrue(any("modalidade" in warning and "opção" in warning.lower() for warning in plan.warnings))

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
        service = FillService(self.store, preflight=stub)
        request_id = service.request_fill(process_id)
        open_command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(
            open_command["id"], {"ok": True, "action": "open_act", "screen": "list"}
        )
        read_command = self.store.claim_extension_command("extension-test")
        service.handle_command_result(read_command["id"], {"ok": True, "identity": IDENTITY, "generation": 4})
        return service, request_id

    def test_a_read_form_with_a_wrong_identity_blocks_before_the_preflight(self):
        stub = StubPreflight(error=AssertionError("o preflight não pode rodar com identidade errada"))
        process_id = self.make_process()
        service = FillService(self.store, preflight=stub)
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
        service = FillService(self.store, preflight=stub)
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
        self.assertEqual(request["state"], "BLOQUEADO")
        self.assertIn("EXISTING_VALUE_DIVERGENCE", request["error"])
        self.assertIn("matricula", request["error"])
        self.assertIsNone(self.store.claim_extension_command("extension-test"))

    def test_a_broken_preflight_moves_the_request_to_erro(self):
        stub = StubPreflight(error=RuntimeError("inesperado"))

        _service, request_id = self.reach_reading(stub)

        request = self.store.get_fill_request(request_id)
        self.assertEqual(request["state"], "ERRO")
        self.assertIn("preflight falhou", request["error"])


if __name__ == "__main__":
    unittest.main()
