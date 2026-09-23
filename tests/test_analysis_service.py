"""Tests for analysis normalization and the Mesa analysis service (M4)."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.analysis import MANDATORY_FIELDS, OPTIONAL_FIELDS
from app.analysis.legacy_adapter import (
    AnalysisError,
    LegacyAnalysisAdapter,
    resolve_tesseract,
    tesseract_candidates,
)
from app.analysis.normalize import normalize_analysis
from app.analysis.service import AnalysisService
from app.core.models import DocumentRecord, ProcessRecord
from app.core.store import Store

DOCUMENTS = [
    {"id": 5, "event": "1", "title": "Ato.pdf"},
    {"id": 6, "event": "9", "title": "Documento_Processo_Portal_Gestor"},
]


def found(value, *, page=2, event="1", document="Ato.pdf", confidence="high"):
    return {
        "value": value,
        "status": "found",
        "confidence": confidence,
        "process": "102390/2026",
        "event": event,
        "document": document,
        "page": page,
        "evidence": {
            "document_id": "doc-1",
            "page": page,
            "quote": value,
            "rects": [[0.1, 0.2, 0.4, 0.25]],
            "method": "text",
            "status": "ready",
        },
    }


def complete_payload(**overrides):
    fields = {name: found(f"valor de {name}") for name in MANDATORY_FIELDS}
    fields.update(overrides)
    return {
        "process": "102390/2026",
        "status": "complete",
        "blocks": [{"interested": "Pessoa Exemplo", "pending": [], "fields": fields}],
    }


class NormalizationTests(unittest.TestCase):
    def test_only_the_blocks_of_the_row_interested_are_kept(self):
        payload = {
            "process": "102390/2026",
            "status": "partial",
            "blocks": [
                {
                    "interested": "Pessoa A",
                    "pending": [],
                    "fields": {name: found(f"valor A de {name}") for name in MANDATORY_FIELDS},
                },
                {
                    "interested": "Pessoa B",
                    "pending": [],
                    "fields": {name: found(f"valor B de {name}") for name in MANDATORY_FIELDS},
                },
            ],
        }

        analysis = normalize_analysis(
            "102390/2026", payload, documents=DOCUMENTS, interested="PESSOA B"
        )

        self.assertEqual(analysis.interested, ["Pessoa B"])
        self.assertEqual(analysis.process_status, "PRONTO")
        self.assertEqual({record.value for record in analysis.fields}, {
            f"valor B de {name}" for name in MANDATORY_FIELDS
        })

    def test_a_row_without_its_block_is_revisar_and_keeps_no_foreign_fields(self):
        payload = complete_payload()
        payload["blocks"][0]["interested"] = "Pessoa A"

        analysis = normalize_analysis(
            "102390/2026", payload, documents=DOCUMENTS, interested="PESSOA B"
        )

        self.assertEqual(analysis.process_status, "REVISAR")
        self.assertEqual(analysis.fields, [])
        self.assertTrue(any("bloco" in warning for warning in analysis.warnings), analysis.warnings)

    def test_without_an_interested_hint_every_block_is_merged(self):
        payload = {
            "process": "102390/2026",
            "status": "partial",
            "blocks": [
                {"interested": "Pessoa A", "pending": [], "fields": {"cargo": found("cargo A")}},
                {"interested": "Pessoa B", "pending": [], "fields": {"matricula": found("matricula B")}},
            ],
        }

        analysis = normalize_analysis("102390/2026", payload, documents=DOCUMENTS)

        self.assertEqual(analysis.interested, ["Pessoa A", "Pessoa B"])
        self.assertEqual({record.field_name for record in analysis.fields}, {"cargo", "matricula"})

    def test_a_complete_result_becomes_pronto_with_evidence(self):
        analysis = normalize_analysis("102390/2026", complete_payload(), documents=DOCUMENTS)

        self.assertEqual(analysis.process_status, "PRONTO")
        self.assertEqual(analysis.pending_fields, [])
        cargo = next(record for record in analysis.fields if record.field_name == "cargo")
        self.assertEqual(cargo.value, "valor de cargo")
        self.assertEqual(cargo.page, 2)
        self.assertEqual(cargo.confidence, 1.0)
        self.assertEqual(cargo.document_id, 5)
        self.assertEqual(cargo.evidence["quote"], "valor de cargo")
        self.assertEqual(cargo.evidence["method"], "text")
        self.assertEqual(analysis.interested, ["Pessoa Exemplo"])
        self.assertEqual(analysis.legacy_status, "complete")

    def test_a_missing_mandatory_field_forces_revisar(self):
        payload = complete_payload()
        del payload["blocks"][0]["fields"]["data_nascimento"]

        analysis = normalize_analysis("102390/2026", payload, documents=DOCUMENTS)

        self.assertEqual(analysis.process_status, "REVISAR")
        self.assertEqual(analysis.pending_fields, ["data_nascimento"])

    def test_a_missing_optional_field_alone_keeps_pronto(self):
        payload = complete_payload()

        analysis = normalize_analysis("102390/2026", payload, documents=DOCUMENTS)

        self.assertEqual(analysis.process_status, "PRONTO")
        self.assertFalse(any(name in analysis.pending_fields for name in OPTIONAL_FIELDS))

    def test_a_field_that_is_not_found_does_not_count_as_ready(self):
        payload = complete_payload()
        payload["blocks"][0]["fields"]["matricula"] = {
            "value": None,
            "status": "missing",
            "confidence": "none",
        }

        analysis = normalize_analysis("102390/2026", payload, documents=DOCUMENTS)

        self.assertEqual(analysis.process_status, "REVISAR")
        self.assertIn("matricula", analysis.pending_fields)

    def test_an_empty_payload_is_revisar_and_never_pronto(self):
        analysis = normalize_analysis("102390/2026", {"status": "partial", "blocks": []})

        self.assertEqual(analysis.process_status, "REVISAR")
        self.assertEqual(analysis.pending_fields, list(MANDATORY_FIELDS))
        self.assertEqual(analysis.fields, [])

    def test_an_empty_value_does_not_count_as_ready(self):
        payload = complete_payload(cargo={"value": "   ", "status": "found", "confidence": "high"})

        analysis = normalize_analysis("102390/2026", payload)

        self.assertEqual(analysis.process_status, "REVISAR")
        self.assertIn("cargo", analysis.pending_fields)

    def test_confidence_vocabulary_maps_to_stable_numbers(self):
        payload = complete_payload(
            cargo=found("Professor", confidence="high"),
            modalidade=found("aposentadoria", confidence="medium"),
            matricula=found("78.710-8/2", confidence="low"),
            data_nascimento=found("16/02/1950", confidence=None),
        )

        analysis = normalize_analysis("102390/2026", payload)
        by_name = {record.field_name: record for record in analysis.fields}

        self.assertEqual(by_name["cargo"].confidence, 1.0)
        self.assertEqual(by_name["modalidade"].confidence, 0.6)
        self.assertEqual(by_name["matricula"].confidence, 0.3)
        self.assertIsNone(by_name["data_nascimento"].confidence)

    def test_a_citation_resolves_the_registered_document(self):
        payload = complete_payload(
            data_nascimento={
                "value": "16/02/1950",
                "status": "found",
                "confidence": "high",
                "citation": {
                    "process": "102390/2026",
                    "event": "9",
                    "page": 1,
                    "document": "Documento_Processo_Portal_Gestor",
                },
            }
        )

        analysis = normalize_analysis("102390/2026", payload, documents=DOCUMENTS)
        record = next(item for item in analysis.fields if item.field_name == "data_nascimento")

        self.assertEqual(record.document_id, 6)
        self.assertEqual(record.page, 1)
        self.assertEqual(record.evidence["citation"]["document"], "Documento_Processo_Portal_Gestor")

    def test_a_citation_resolves_title_when_spacing_and_hyphens_differ(self):
        documents = [{"id": 14733, "event": "1", "title": "Volume-Digitalizado-1"}]
        payload = complete_payload(
            cargo={
                "value": "aposentadoria voluntária",
                "status": "found",
                "event": "1",
                "document": "Volume Digitalizado - 1  ",
                "page": 90,
            }
        )

        analysis = normalize_analysis("004731/2024", payload, documents=documents)
        record = next(item for item in analysis.fields if item.field_name == "cargo")

        self.assertEqual(record.document_id, 14733)
        self.assertEqual(record.page, 90)

    def test_ambiguous_normalized_document_titles_are_not_linked(self):
        documents = [
            {"id": 14733, "event": "1", "title": "Volume-Digitalizado-1"},
            {"id": 14737, "event": "1", "title": "Volume Digitalizado 1"},
        ]
        payload = complete_payload(
            cargo={
                "value": "aposentadoria voluntária",
                "status": "found",
                "event": "1",
                "document": "Volume.Digitalizado-1",
                "page": 90,
            }
        )

        analysis = normalize_analysis("004731/2024", payload, documents=documents)
        record = next(item for item in analysis.fields if item.field_name == "cargo")

        self.assertIsNone(record.document_id)

    def test_event_only_source_is_not_linked_when_the_event_has_multiple_documents(self):
        documents = [
            {"id": 14733, "event": "1", "title": "Volume-Digitalizado-1"},
            {"id": 14737, "event": "1", "title": "Anexo.pdf"},
        ]
        payload = complete_payload(
            cargo={"value": "aposentadoria voluntária", "status": "found", "event": "1"}
        )

        analysis = normalize_analysis("004731/2024", payload, documents=documents)
        record = next(item for item in analysis.fields if item.field_name == "cargo")

        self.assertIsNone(record.document_id)

    def test_an_unregistered_document_is_reported_as_a_warning(self):
        payload = complete_payload(cargo=found("Professor", document="Sumiu.pdf"))

        analysis = normalize_analysis("102390/2026", payload, documents=DOCUMENTS)
        record = next(item for item in analysis.fields if item.field_name == "cargo")

        self.assertIsNone(record.document_id)
        self.assertTrue(any("não está registrado" in warning for warning in analysis.warnings))

    def test_unknown_fields_are_reported_without_changing_readiness(self):
        payload = complete_payload(extra=found("algo"))

        analysis = normalize_analysis("102390/2026", payload)

        self.assertEqual(analysis.process_status, "PRONTO")
        self.assertTrue(any("campo desconhecido" in warning for warning in analysis.warnings))

    def test_multiple_blocks_are_merged_with_every_interested_person(self):
        payload = complete_payload()
        payload["blocks"].append(
            {
                "interested": "Outra Pessoa",
                "pending": [],
                "fields": {name: found(f"outro {name}") for name in MANDATORY_FIELDS},
            }
        )

        analysis = normalize_analysis("102390/2026", payload)

        self.assertEqual(analysis.interested, ["Pessoa Exemplo", "Outra Pessoa"])
        self.assertEqual(analysis.process_status, "PRONTO")
        self.assertEqual(len(analysis.fields), 2 * len(MANDATORY_FIELDS))


class LegacyAdapterTests(unittest.TestCase):
    def test_tesseract_resolution_reports_every_candidate(self):
        candidates = tesseract_candidates("data", "C:/repo")

        # Only supported locations: the data root and the packaged runtime next
        # to START.cmd. The legacy portable tree was dropped in M6 Task 8 prep.
        self.assertEqual(len(candidates), 2)
        self.assertTrue(str(candidates[0]).replace("\\", "/").endswith("data/runtime/tesseract"))
        self.assertTrue(str(candidates[1]).replace("\\", "/").endswith("repo/runtime/tesseract"))
        for candidate in candidates:
            self.assertNotIn("tce-extractor", str(candidate))

    def test_a_missing_tesseract_fails_closed(self):
        with self.assertRaises(AnalysisError):
            resolve_tesseract("data-de-teste-que-nao-existe", "C:/repo-inexistente")

    def test_the_adapter_points_at_the_canonical_archive(self):
        adapter = LegacyAnalysisAdapter("data", repo_root="C:/repo")

        self.assertTrue(str(adapter.archive_root).replace("\\", "/").endswith("data/archive"))

    def test_the_adapter_never_imports_the_legacy_module_eagerly(self):
        adapter = LegacyAnalysisAdapter("data", repo_root="C:/repo")

        # Construction must not touch sys.path or import a browser-era module.
        self.assertFalse(hasattr(adapter, "_module_loaded"))


class FakeAdapter:
    """Duck-typed stand-in for LegacyAnalysisAdapter (no Tesseract needed)."""

    def __init__(self, payloads=None, error=None):
        self.payloads = payloads or {}
        self.error = error
        self.calls = []

    def analyze(self, process_key, **kwargs):
        # The service passes the canonical rows so the real adapter can render
        # the engine's execution view; this stub records only the key.
        self.calls.append(process_key)
        if self.error is not None:
            raise self.error
        return self.payloads.get(process_key, complete_payload())


class AnalysisServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        (self.data / "archive").mkdir(parents=True, exist_ok=True)
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.process_id = self.store.upsert_process(
            ProcessRecord(
                process_key="102390/2026",
                interested="Pessoa Exemplo",
                interested_normalized="pessoa exemplo",
                status="DOWNLOADED",
            )
        )
        self.store.replace_documents(
            self.process_id,
            [
                DocumentRecord(
                    source_id="102390/2026|1|Ato",
                    title="Ato.pdf",
                    relative_path="archive/processos/102390-2026/Ato.pdf",
                    sha256="a" * 64,
                    page_count=3,
                    event="1",
                )
            ],
        )

    def build(self, adapter):
        return AnalysisService(self.store, self.data, adapter=adapter)

    def test_each_interested_row_keeps_only_its_own_block(self):
        second_id = self.store.upsert_process(
            ProcessRecord(
                process_key="102390/2026",
                interested="Outra Pessoa",
                interested_normalized="outra pessoa",
                status="DOWNLOADED",
            )
        )
        payload = {
            "process": "102390/2026",
            "status": "partial",
            "blocks": [
                {
                    "interested": "Pessoa Exemplo",
                    "pending": [],
                    "fields": {name: found(f"valor de exemplo {name}") for name in MANDATORY_FIELDS},
                },
                {
                    "interested": "Outra Pessoa",
                    "pending": [],
                    "fields": {name: found(f"valor da outra {name}") for name in MANDATORY_FIELDS},
                },
            ],
        }
        service = self.build(FakeAdapter({"102390/2026": payload}))

        service.analyze_one(self.process_id)
        service.analyze_one(second_id)

        first = {record["value"] for record in self.store.get_process(self.process_id)["fields"]}
        second = {record["value"] for record in self.store.get_process(second_id)["fields"]}
        self.assertTrue(all("exemplo" in value for value in first), first)
        self.assertTrue(all("outra" in value for value in second), second)

    def test_a_complete_result_stores_fields_and_moves_to_pronto(self):
        service = self.build(FakeAdapter())

        status = service.analyze_one(self.process_id)

        self.assertEqual(status, "PRONTO")
        process = self.store.get_process(self.process_id)
        self.assertEqual(process["status"], "PRONTO")
        self.assertEqual(len(process["fields"]), len(MANDATORY_FIELDS))
        cargo = next(field for field in process["fields"] if field["field_name"] == "cargo")
        self.assertEqual(cargo["document_id"], process["documents"][0]["id"])
        events = [event["event_type"] for event in process["events"]]
        self.assertEqual(events, ["analysis_started", "analysis_finished"])

    def test_a_missing_mandatory_field_results_in_revisar(self):
        payload = complete_payload()
        del payload["blocks"][0]["fields"]["data_nascimento"]
        service = self.build(FakeAdapter({"102390/2026": payload}))

        status = service.analyze_one(self.process_id)

        self.assertEqual(status, "REVISAR")
        process = self.store.get_process(self.process_id)
        self.assertEqual(process["status"], "REVISAR")
        self.assertEqual(process["events"][-1]["payload"]["pending"], ["data_nascimento"])

    def test_an_engine_failure_moves_the_process_to_erro(self):
        service = self.build(FakeAdapter(error=RuntimeError("sem tesseract")))

        with self.assertRaises(RuntimeError):
            service.analyze_one(self.process_id)

        process = self.store.get_process(self.process_id)
        self.assertEqual(process["status"], "ERRO")
        self.assertEqual(process["events"][-1]["event_type"], "analysis_failed")

    def test_enqueue_runs_the_worker_and_finishes_the_job(self):
        self.store.set_process_acquisition_state(self.process_id, "DOWNLOADED")
        service = self.build(FakeAdapter())

        job_id = service.enqueue(self.process_id)
        service.drain()

        job = self.store.get_job(job_id)
        self.assertEqual(job["job_type"], "analysis")
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(job["completed"], 1)
        process = self.store.get_process(self.process_id)
        self.assertEqual(process["status"], "PRONTO")
        self.assertEqual(
            process["acquisition_state"],
            "DOWNLOADED",
            "analysis progress must not make downloaded bytes look pending",
        )

    def test_a_failed_item_does_not_stop_the_job(self):
        second = self.store.upsert_process(
            ProcessRecord(
                process_key="102391/2026",
                interested="Outra Pessoa",
                interested_normalized="outra pessoa",
                status="DOWNLOADED",
            )
        )
        service = self.build(FakeAdapter(error=RuntimeError("motor indisponível")))
        job_id = service._jobs.create("analysis", [self.process_id, second])

        service.run(job_id)

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(job["failed"], 2)
        states = {
            int(item["process_id"]): item["state"]
            for item in self.store.list_job_items(job_id)
        }
        self.assertEqual(states[self.process_id], "FAILED")
        self.assertEqual(states[second], "FAILED")


if __name__ == "__main__":
    unittest.main()
