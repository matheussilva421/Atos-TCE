"""Tests for analysis normalization and the Mesa analysis service (M4)."""

import unittest

from app.analysis import MANDATORY_FIELDS, OPTIONAL_FIELDS
from app.analysis.legacy_adapter import (
    AnalysisError,
    LegacyAnalysisAdapter,
    resolve_tesseract,
    tesseract_candidates,
)
from app.analysis.normalize import normalize_analysis

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

        self.assertEqual(len(candidates), 3)
        self.assertTrue(str(candidates[0]).replace("\\", "/").endswith("data/runtime/tesseract"))

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


if __name__ == "__main__":
    unittest.main()
