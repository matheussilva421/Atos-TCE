import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from evidence_geometry import (  # noqa: E402
    build_visual_evidence,
    locate_evidence,
    read_page_words,
)


class EvidenceGeometryTests(unittest.TestCase):
    def test_repeated_quote_is_not_guessed(self):
        words = [
            {"text": "103.870-2/1", "rect": [0.1, 0.1, 0.3, 0.2]},
            {"text": "103.870-2/1", "rect": [0.1, 0.5, 0.3, 0.6]},
        ]
        self.assertEqual(locate_evidence(words, "103.870-2/1"), [])

    def test_unique_quote_returns_normalized_rectangles(self):
        words = [
            {"text": "Concede", "rect": [10, 20, 50, 40]},
            {"text": "aposentadoria", "rect": [55, 20, 125, 40]},
        ]
        self.assertEqual(
            locate_evidence(words, "Concede aposentadoria", page_width=200, page_height=100),
            [[0.05, 0.2, 0.625, 0.4]],
        )

    def test_native_pdf_words_include_text_and_page_geometry(self):
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover - environment gate
            self.skipTest(f"PyMuPDF indisponível: {exc}")
        with TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "fixture.pdf"
            document = pymupdf.open()
            page = document.new_page(width=200, height=100)
            page.insert_text((10, 30), "Ato complementar")
            document.save(pdf_path)
            document.close()
            result = read_page_words(pdf_path, 0, tesseract=None, tessdata=None)
        self.assertEqual(result["page"], 0)
        self.assertIn("Ato complementar", result["text"])
        self.assertTrue(result["words"])
        self.assertTrue(all(0 <= value <= 1 for word in result["words"] for value in word["rect"]))

    def test_visual_sidecar_uses_occurrence_identity_and_relative_paths(self):
        records = [
            {
                "record_id": "record-1",
                "process_key": "103439/2023",
                "interested_normalized": "SILVIA MARIA",
                "fields": {
                    "cargo": {
                        "value": "PROFESSOR",
                        "status": "found",
                        "event": "6",
                        "document": "Documento_Processo.pdf",
                        "page": 2,
                        "quote": "PROFESSOR",
                        "rects": [[0.1, 0.2, 0.4, 0.3]],
                    }
                },
            }
        ]
        documents = [
            {
                "process_key": "103439/2023",
                "event_id": "6",
                "document_id": "portal-doc-1",
                "pdf_sha256": hashlib.sha256(b"pdf").hexdigest(),
                "relative_path": "documentos/Documento_Processo.pdf",
                "page_count": 3,
            }
        ]
        result = build_visual_evidence(records, documents)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(len(result["documents"]), 1)
        document_id = next(iter(result["documents"]))
        self.assertEqual(
            document_id,
            hashlib.sha256(
                (
                    "103439/2023|6|portal-doc-1|"
                    + hashlib.sha256(b"pdf").hexdigest()
                ).encode()
            ).hexdigest(),
        )
        self.assertEqual(result["documents"][document_id]["relative_path"], "documentos/Documento_Processo.pdf")
        self.assertEqual(result["records"]["record-1"]["cargo"]["document_id"], document_id)
        self.assertNotIn("C:\\", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
