import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from evidence_geometry import (  # noqa: E402
    build_visual_evidence,
    locate_evidence,
    read_page_words,
)


class EvidenceGeometryTests(unittest.TestCase):
    def test_one_page_pdf_has_one_page_context_and_unique_evidence(self):
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover - environment gate
            self.skipTest(f"PyMuPDF indisponível: {exc}")
        with TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "one-page.pdf"
            document = pymupdf.open()
            page = document.new_page(width=200, height=100)
            page.insert_text((10, 30), "MATRICULA 1038702/1")
            document.save(pdf_path)
            document.close()

            reopened = pymupdf.open(pdf_path)
            self.assertEqual(len(reopened), 1)
            reopened.close()
            result = read_page_words(pdf_path, 0, tesseract=None, tessdata=None)

        self.assertEqual(result["page"], 0)
        self.assertEqual(result["rotation"], 0)
        self.assertEqual(result["method"], "native")
        self.assertEqual(len(locate_evidence(result["words"], "MATRICULA 1038702/1")), 1)

    def test_repeated_quote_is_not_guessed(self):
        words = [
            {"text": "103.870-2/1", "rect": [0.1, 0.1, 0.3, 0.2]},
            {"text": "103.870-2/1", "rect": [0.1, 0.5, 0.3, 0.6]},
        ]
        self.assertEqual(locate_evidence(words, "103.870-2/1"), [])

    def test_repeated_multiword_quote_is_not_guessed_between_candidates(self):
        words = [
            {"text": "Cargo:", "rect": [0.1, 0.1, 0.2, 0.2]},
            {"text": "PROFESSOR", "rect": [0.21, 0.1, 0.5, 0.2]},
            {"text": "Cargo:", "rect": [0.1, 0.6, 0.2, 0.7]},
            {"text": "PROFESSOR", "rect": [0.21, 0.6, 0.5, 0.7]},
        ]
        self.assertEqual(locate_evidence(words, "Cargo: PROFESSOR"), [])

    def test_unique_quote_returns_normalized_rectangles(self):
        words = [
            {"text": "Concede", "rect": [10, 20, 50, 40]},
            {"text": "aposentadoria", "rect": [55, 20, 125, 40]},
        ]
        self.assertEqual(
            locate_evidence(words, "Concede aposentadoria", page_width=200, page_height=100),
            [[0.05, 0.2, 0.625, 0.4]],
        )

    def test_out_of_bounds_rect_invalidates_the_match_instead_of_clamping(self):
        words = [{"text": "PROFESSOR", "rect": [101, 10, 130, 20]}]
        self.assertEqual(
            locate_evidence(words, "PROFESSOR", page_width=100, page_height=100),
            [],
        )

    def test_low_confidence_ocr_word_does_not_get_highlighted(self):
        words = [{
            "text": "PROFESSOR",
            "rect": [0.1, 0.1, 0.5, 0.2],
            "confidence": 24.0,
            "method": "ocr",
        }]
        self.assertEqual(locate_evidence(words, "PROFESSOR"), [])

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

    def test_native_words_follow_cropbox_and_rotation_in_display_coordinates(self):
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover - environment gate
            self.skipTest(f"PyMuPDF indisponível: {exc}")
        with TemporaryDirectory() as temporary:
            for rotation, predicate in (
                (90, lambda rect: rect[0] > 0.5 and rect[1] < 0.2),
                (180, lambda rect: rect[2] > 0.8 and rect[1] > 0.6),
                (270, lambda rect: rect[0] < 0.4 and rect[1] > 0.5),
            ):
                pdf_path = Path(temporary) / f"rotated-{rotation}.pdf"
                document = pymupdf.open()
                page = document.new_page(width=200, height=100)
                page.insert_text((30, 30), "ROTATED EVIDENCE")
                page.set_cropbox(pymupdf.Rect(20, 10, 180, 90))
                page.set_rotation(rotation)
                document.save(pdf_path)
                document.close()

                result = read_page_words(pdf_path, 0, tesseract=None, tessdata=None)
                self.assertEqual(result["rotation"], rotation)
                self.assertTrue(result["words"])
                self.assertTrue(predicate(result["words"][0]["rect"]), result)

    def test_native_words_apply_exact_display_transform_for_all_right_angle_rotations(self):
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover - environment gate
            self.skipTest(f"PyMuPDF indisponível: {exc}")
        with TemporaryDirectory() as temporary:
            baseline_path = Path(temporary) / "rotation-0.pdf"
            document = pymupdf.open()
            page = document.new_page(width=200, height=100)
            page.insert_text((30, 30), "ROTATED EVIDENCE")
            page.set_cropbox(pymupdf.Rect(20, 10, 180, 90))
            document.save(baseline_path)
            document.close()
            baseline = read_page_words(baseline_path, 0, tesseract=None, tessdata=None)
            baseline_word = next(word for word in baseline["words"] if word["text"] == "ROTATED")
            raw = [
                baseline_word["rect"][0] * baseline["width"],
                baseline_word["rect"][1] * baseline["height"],
                baseline_word["rect"][2] * baseline["width"],
                baseline_word["rect"][3] * baseline["height"],
            ]

            for rotation in (90, 180, 270):
                pdf_path = Path(temporary) / f"rotation-{rotation}.pdf"
                document = pymupdf.open()
                page = document.new_page(width=200, height=100)
                page.insert_text((30, 30), "ROTATED EVIDENCE")
                page.set_cropbox(pymupdf.Rect(20, 10, 180, 90))
                page.set_rotation(rotation)
                document.save(pdf_path)
                document.close()

                result = read_page_words(pdf_path, 0, tesseract=None, tessdata=None)
                actual = next(word for word in result["words"] if word["text"] == "ROTATED")["rect"]
                width, height = baseline["width"], baseline["height"]
                if rotation == 90:
                    display = [height - raw[3], raw[0], height - raw[1], raw[2]]
                elif rotation == 180:
                    display = [width - raw[2], height - raw[3], width - raw[0], height - raw[1]]
                else:
                    display = [raw[1], width - raw[2], raw[3], width - raw[0]]
                display_width = height if rotation in (90, 270) else width
                display_height = width if rotation in (90, 270) else height
                expected = [
                    display[0] / display_width,
                    display[1] / display_height,
                    display[2] / display_width,
                    display[3] / display_height,
                ]
                self.assertEqual(result["rotation"], rotation)
                for actual_value, expected_value in zip(actual, expected):
                    self.assertAlmostEqual(actual_value, expected_value, places=6)

    def test_scanned_page_uses_one_tsv_ocr_result_for_text_and_geometry(self):
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover - environment gate
            self.skipTest(f"PyMuPDF indisponível: {exc}")
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\t"
            "top\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t20\t10\t80\t20\t96\tPROFESSOR\n"
        )
        with TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "scanned.pdf"
            document = pymupdf.open()
            document.new_page(width=200, height=100)
            document.save(pdf_path)
            document.close()

            with patch(
                "evidence_geometry.subprocess.run",
                return_value=type("Completed", (), {"returncode": 0, "stdout": tsv})(),
            ) as run:
                result = read_page_words(
                    pdf_path,
                    0,
                    tesseract="fixture-tesseract",
                    tessdata="fixture-tessdata",
                )

        self.assertEqual(result["method"], "ocr")
        self.assertEqual(result["text"], "PROFESSOR")
        self.assertEqual(result["words"], [{
            "text": "PROFESSOR",
            "rect": [0.05, 0.05, 0.25, 0.15],
            "confidence": 96.0,
            "method": "ocr",
        }])
        run.assert_called_once()
        self.assertIn("tsv", run.call_args.args[0])

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
