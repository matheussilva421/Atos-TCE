import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).parent
APP_ROOT = REPO_ROOT / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from legal_context import build_legal_contexts, write_legal_contexts  # noqa: E402


DATASET_SHA256 = "d" * 64
PDF_SHA256 = "a" * 64


def _resolution_document(*, event: str = "9", document_id: str = "resolution-9", sha256: str = PDF_SHA256) -> dict:
    return {
        "event": event,
        "event_id": event,
        "id": document_id,
        "title": "RESOLUCAO ADMINISTRATIVA SINTETICA",
        "classification": "resolucao_administrativa",
        "automatic_source": True,
        "sha256": sha256,
        "page_count": 2,
    }


def _guide_document() -> dict:
    return {
        "event": "12",
        "event_id": "12",
        "id": "guide-12",
        "title": "GUIA FINANCEIRA TAXACAO SINTETICA",
        "classification": "guia_financeira_taxacao",
        "automatic_source": True,
        "sha256": "b" * 64,
        "page_count": 1,
    }


def _manifest(*documents: dict) -> dict:
    return {
        "version": 1,
        "processes": [{"process": "103439/2023", "documents": list(documents)}],
    }


def _checkpoint(
    *,
    interested: str = "MARIA DA SILVA",
    fields: dict | None = None,
    identifier: str | None = None,
) -> dict:
    block = {"interested": interested, "fields": fields or {}}
    if identifier is not None:
        block["interested_identifier"] = identifier
    return {
        "processes": {
            "103439/2023": {
                "result": {
                    "process": "103439/2023",
                    "blocks": [block],
                }
            }
        }
    }


def _foundation_field(*, event: str = "9", document: str = "resolution-9") -> dict:
    return {
        "status": "found",
        "value": "Nos termos do art. 6º da lei estadual",
        "quote": "Nos termos do art. 6º da lei estadual",
        "process": "103439/2023",
        "event": event,
        "document": document,
        "page": 1,
    }


class LegalContextTests(unittest.TestCase):
    def test_keeps_all_resolution_pages_and_operational_text_beyond_truncated_field_quote(self):
        document = _resolution_document()
        manifest = _manifest(document)
        checkpoint = _checkpoint(fields={"fundamento_legal": _foundation_field()})
        page_texts = {
            "resolution-9": {
                "pdf_sha256": PDF_SHA256,
                "pages": [
                    "RESOLUCAO ADMINISTRATIVA SINTETICA\nInteressada: MARIA DA SILVA\nPreâmbulo.\nRESOLVE:",
                    "Art. 1º A concessão é fundamentada no art. 6º, § 5º, e alcança ambos os requisitos."
                    + (" Texto operativo preservado." * 32),
                ],
            }
        }

        contexts = build_legal_contexts(manifest, checkpoint, page_texts, DATASET_SHA256)

        self.assertEqual(len(contexts["records"]), 1)
        record = contexts["records"][0]
        self.assertEqual(contexts["schema_version"], 1)
        self.assertEqual(contexts["dataset_sha256"], DATASET_SHA256)
        self.assertEqual(record["process_key"], "103439/2023")
        self.assertEqual(record["interested_normalized"], "maria da silva")
        self.assertEqual(record["resolution_status"], "complete")
        self.assertEqual(len(record["pages"]), 2)
        self.assertEqual(record["pages"][1]["citation"]["document_id"], "resolution-9")
        self.assertEqual(record["pages"][1]["citation"]["event_id"], "9")
        self.assertIn("§ 5º", record["operative_text"])
        self.assertIn("ambos", record["operative_text"])
        self.assertGreater(len(record["operative_text"]), 512)
        self.assertEqual(record["dataset_sha256"], DATASET_SHA256)
        self.assertTrue(record["extraction_version"])

    def test_does_not_mark_context_complete_when_interested_is_absent_from_resolution_pages(self):
        document = _resolution_document()
        contexts = build_legal_contexts(
            _manifest(document),
            _checkpoint(fields={"fundamento_legal": _foundation_field()}),
            {
                "resolution-9": {
                    "pdf_sha256": PDF_SHA256,
                    "pages": [
                        "RESOLUCAO ADMINISTRATIVA SINTETICA\nRESOLVE: Art. 6º.",
                        "Ato operativo sem identificação nominal.",
                    ],
                }
            },
            DATASET_SHA256,
        )

        self.assertEqual(contexts["records"][0]["resolution_status"], "incomplete")

    def test_uses_name_token_boundaries_instead_of_matching_embedded_names(self):
        document = _resolution_document()
        contexts = build_legal_contexts(
            _manifest(document),
            _checkpoint(interested="ANA", fields={"fundamento_legal": _foundation_field()}),
            {
                "resolution-9": {
                    "pdf_sha256": PDF_SHA256,
                    "pages": [
                        "Interessada: MARIANA DA SILVA\nRESOLVE:",
                        "Art. 1º Conceder o benefício.",
                    ],
                }
            },
            DATASET_SHA256,
        )

        self.assertEqual(contexts["records"][0]["resolution_status"], "incomplete")

        exact = build_legal_contexts(
            _manifest(document),
            _checkpoint(interested="ANA", fields={"fundamento_legal": _foundation_field()}),
            {
                "resolution-9": {
                    "pdf_sha256": PDF_SHA256,
                    "pages": [
                        "Interessada: ANA\nRESOLVE:",
                        "Art. 1º Conceder o benefício.",
                    ],
                }
            },
            DATASET_SHA256,
        )

        self.assertEqual(exact["records"][0]["resolution_status"], "complete")

    def test_marks_same_name_on_multiple_resolution_sources_as_conflict_without_identifier(self):
        first = _resolution_document(event="9", document_id="resolution-9")
        second = _resolution_document(
            event="10", document_id="resolution-10", sha256="b" * 64
        )
        first["page_count"] = second["page_count"] = 1
        contexts = build_legal_contexts(
            _manifest(first, second),
            _checkpoint(interested="ANA"),
            {
                "resolution-9": {
                    "pdf_sha256": first["sha256"],
                    "pages": ["Interessada: ANA\nRESOLVE:\nArt. 1º Conceder."],
                },
                "resolution-10": {
                    "pdf_sha256": second["sha256"],
                    "pages": ["Interessada: ANA\nRESOLVE:\nArt. 1º Conceder."],
                },
            },
            DATASET_SHA256,
        )

        self.assertEqual(contexts["records"][0]["resolution_status"], "conflict")

    def test_uses_identifier_to_disambiguate_homonymous_resolution_sources(self):
        first = _resolution_document(event="9", document_id="resolution-9")
        second = _resolution_document(
            event="10", document_id="resolution-10", sha256="b" * 64
        )
        first["page_count"] = second["page_count"] = 1
        contexts = build_legal_contexts(
            _manifest(first, second),
            _checkpoint(interested="ANA", identifier="103.870-2/1"),
            {
                "resolution-9": {
                    "pdf_sha256": first["sha256"],
                    "pages": ["Interessada: ANA\nMatrícula: 103.870-2/0\nRESOLVE:\nArt. 1º."],
                },
                "resolution-10": {
                    "pdf_sha256": second["sha256"],
                    "pages": ["Interessada: ANA\nMatrícula: 1038702/1\nRESOLVE:\nArt. 1º."],
                },
            },
            DATASET_SHA256,
        )

        record = contexts["records"][0]
        self.assertEqual(record["resolution_status"], "complete")
        self.assertEqual(
            record["pages"][0]["citation"]["document_id"], "resolution-10"
        )

    def test_extracts_operativo_block_after_historical_resolve_marker(self):
        document = _resolution_document()
        contexts = build_legal_contexts(
            _manifest(document),
            _checkpoint(fields={"fundamento_legal": _foundation_field()}),
            {
                "resolution-9": {
                    "pdf_sha256": PDF_SHA256,
                    "pages": [
                        "No ato anterior, resolve: arquivar o pedido histórico.",
                        "RESOLVE:\nArt. 1º Conceder o benefício vigente.",
                    ],
                }
            },
            DATASET_SHA256,
        )

        operative_text = contexts["records"][0]["operative_text"]
        self.assertEqual(
            operative_text,
            "RESOLVE:\nArt. 1º Conceder o benefício vigente.",
        )

    def test_validates_manifest_page_count_when_page_text_list_is_truncated(self):
        document = _resolution_document()
        document["page_count"] = 3
        contexts = build_legal_contexts(
            _manifest(document),
            _checkpoint(fields={"fundamento_legal": _foundation_field()}),
            {
                "resolution-9": {
                    "pdf_sha256": PDF_SHA256,
                    "pages": [
                        "Interessada: MARIA DA SILVA\nRESOLVE:",
                        "Art. 1º Página disponível.",
                    ],
                }
            },
            DATASET_SHA256,
        )

        record = contexts["records"][0]
        self.assertEqual(len(record["pages"]), 3)
        self.assertEqual(record["pages"][2]["text"], "")
        self.assertEqual(record["resolution_status"], "incomplete")

    def test_does_not_use_a_financial_guide_as_resolution_source(self):
        guide = _guide_document()
        contexts = build_legal_contexts(
            _manifest(guide),
            _checkpoint(fields={"fundamento_legal": _foundation_field(event="12", document="guide-12")}),
            {
                "guide-12": {
                    "pdf_sha256": guide["sha256"],
                    "pages": ["GUIA FINANCEIRA TAXACAO\nRESOLVE valores"],
                }
            },
            DATASET_SHA256,
        )

        self.assertEqual(contexts["records"][0]["resolution_status"], "missing")
        self.assertEqual(contexts["records"][0]["pages"], [])
        self.assertEqual(contexts["records"][0]["operative_text"], "")

    def test_marks_two_divergent_resolutions_as_conflict(self):
        first = _resolution_document(event="9", document_id="resolution-9")
        second = _resolution_document(
            event="10", document_id="resolution-10", sha256="b" * 64
        )
        first["page_count"] = 1
        second["page_count"] = 1
        fields = {
            "fundamento_legal": {
                "status": "conflict",
                "value": None,
                "candidates": [
                    _foundation_field(event="9", document="resolution-9"),
                    _foundation_field(event="10", document="resolution-10"),
                ],
            }
        }
        contexts = build_legal_contexts(
            _manifest(first, second),
            _checkpoint(fields=fields),
            {
                "resolution-9": {"pdf_sha256": first["sha256"], "pages": ["RESOLVE: Art. 6º."]},
                "resolution-10": {"pdf_sha256": second["sha256"], "pages": ["RESOLVE: Art. 47."]},
            },
            DATASET_SHA256,
        )

        record = contexts["records"][0]
        self.assertEqual(record["resolution_status"], "conflict")
        self.assertEqual(len(record["pages"]), 2)
        self.assertIn("Art. 6º", record["operative_text"])
        self.assertIn("Art. 47", record["operative_text"])

    def test_keeps_failed_ocr_page_as_empty_evidence_and_blocks_completeness(self):
        document = _resolution_document()
        contexts = build_legal_contexts(
            _manifest(document),
            _checkpoint(fields={"fundamento_legal": _foundation_field()}),
            {
                "resolution-9": {
                    "pdf_sha256": document["sha256"],
                    "pages": [
                        "RESOLVE: Art. 6º.",
                        {"text": None, "status": "failed"},
                    ],
                }
            },
            DATASET_SHA256,
        )

        record = contexts["records"][0]
        self.assertEqual(record["resolution_status"], "incomplete")
        self.assertEqual(record["pages"][1]["text"], "")
        self.assertNotIn("§ 5º", record["operative_text"])

    def test_rejects_page_text_with_incompatible_pdf_hash(self):
        document = _resolution_document()
        contexts = build_legal_contexts(
            _manifest(document),
            _checkpoint(fields={"fundamento_legal": _foundation_field()}),
            {
                "resolution-9": {
                    "pdf_sha256": "b" * 64,
                    "pages": ["RESOLVE: Art. 6º, § 5º."],
                }
            },
            DATASET_SHA256,
        )

        record = contexts["records"][0]
        self.assertEqual(record["resolution_status"], "incomplete")
        self.assertEqual(record["pages"], [])
        self.assertEqual(record["operative_text"], "")

    def test_writes_sidecar_atomically_and_leaves_no_partial_temp_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fundamentos-contexto.v1.json"
            contexts = {
                "schema_version": 1,
                "dataset_sha256": DATASET_SHA256,
                "records": [],
            }

            self.assertIsNone(write_legal_contexts(path, contexts))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), contexts)
            self.assertEqual(list(Path(temporary).glob(".fundamentos-contexto.v1.json.*.tmp")), [])

    def test_cleans_temporary_file_when_serialization_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fundamentos-contexto.v1.json"
            with patch("legal_context.json.dump", side_effect=TypeError("fixture serialization failure")):
                with self.assertRaises(TypeError):
                    write_legal_contexts(path, {"records": object()})

            self.assertFalse(path.exists())
            self.assertEqual(list(Path(temporary).glob(".fundamentos-contexto.v1.json.*.tmp")), [])

    def test_cleans_temporary_file_when_fsync_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fundamentos-contexto.v1.json"
            with patch("legal_context.os.fsync", side_effect=OSError("fixture fsync failure")):
                with self.assertRaises(OSError):
                    write_legal_contexts(path, {"schema_version": 1, "records": []})

            self.assertFalse(path.exists())
            self.assertEqual(list(Path(temporary).glob(".fundamentos-contexto.v1.json.*.tmp")), [])

    def test_citation_uses_safe_document_basename_without_exporting_absolute_path(self):
        document = _resolution_document()
        document["id"] = r"C:\private\archive\resolution-9.pdf"
        contexts = build_legal_contexts(
            _manifest(document),
            _checkpoint(fields={"fundamento_legal": _foundation_field(document="resolution-9.pdf")}),
            {
                "resolution-9.pdf": {
                    "pdf_sha256": document["sha256"],
                    "pages": ["RESOLVE: Art. 6º."],
                }
            },
            DATASET_SHA256,
        )

        serialized = json.dumps(contexts, ensure_ascii=False)
        self.assertNotIn(r"C:\private\archive", serialized)
        self.assertEqual(
            contexts["records"][0]["pages"][0]["citation"]["document_id"],
            "resolution-9.pdf",
        )


if __name__ == "__main__":
    unittest.main()
