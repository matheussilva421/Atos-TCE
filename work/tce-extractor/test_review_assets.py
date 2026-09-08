import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from html_generator import build_interface_payload, render_html


class ReviewAssetTests(unittest.TestCase):
    def test_payload_exposes_document_identity_and_visual_evidence_without_changing_v1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "acervo-tce" / "processos" / "103439-2023" / "evento-0009"
            archive.mkdir(parents=True)
            pdf = archive / "resolucao.pdf"
            pdf.write_bytes(b"fixture")
            sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
            document_id = hashlib.sha256(
                f"103439/2023|9|doc-9|{sha256}".encode()
            ).hexdigest()
            record_id = hashlib.sha256("103439/2023|joana da silva".encode()).hexdigest()

            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "processes": [
                            {
                                "process": "103439/2023",
                                "documents": [
                                    {
                                        "event": "9",
                                        "id": "doc-9",
                                        "title": "RESOLUÇÃO ADMINISTRATIVA",
                                        "classification": "resolucao_administrativa",
                                        "relative_path": pdf.relative_to(root / "acervo-tce").as_posix(),
                                        "pdf_path": str(pdf),
                                        "sha256": sha256,
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "processes": {
                            "103439/2023": {
                                "status": "partial",
                                "result": {
                                    "blocks": [
                                        {
                                            "interested": "JOANA DA SILVA",
                                            "fields": {
                                                "cargo": {
                                                    "status": "found",
                                                    "value": "PROFESSORA",
                                                    "process": "103439/2023",
                                                    "event": "9",
                                                    "document": "RESOLUÇÃO ADMINISTRATIVA",
                                                    "page": 1,
                                                    "quote": "PROFESSORA",
                                                }
                                            },
                                        }
                                    ]
                                },
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            sidecar = root / "evidencias-visuais.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "documents": {
                            document_id: {
                                "document_id": document_id,
                                "process_key": "103439/2023",
                                "event_id": "9",
                                "sha256": sha256,
                                "relative_path": pdf.relative_to(root / "acervo-tce").as_posix(),
                                "page_count": 1,
                            }
                        },
                        "records": {
                            record_id: {
                                "cargo": {
                                    "document_id": document_id,
                                    "page": 1,
                                    "quote": "PROFESSORA",
                                    "rects": [[0.1, 0.2, 0.4, 0.25]],
                                    "method": "native",
                                    "status": "found",
                                }
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = build_interface_payload(
                manifest,
                checkpoint,
                visual_evidence_path=sidecar,
            )
            document = payload["processes"][0]["documents"][0]
            field = payload["processes"][0]["blocks"][0]["fields"]["cargo"]
            self.assertEqual(document["document_id"], document_id)
            self.assertEqual(field["evidence"]["document_id"], document_id)
            self.assertEqual(field["evidence"]["rects"], [[0.1, 0.2, 0.4, 0.25]])
            self.assertEqual(payload["review_assets"]["mode"], "offline-pdfjs-with-iframe-fallback")
            self.assertNotIn("evidence", payload["processes"][0]["blocks"][0]["fields"]["cargo"].get("v1", {}))

            html = render_html(payload)
            self.assertIn("offline-pdfjs-with-iframe-fallback", html)
            self.assertIn("pdf-canvas", html)
            self.assertIn("document_id", html)
            self.assertIn("data-review-mode", html)


if __name__ == "__main__":
    unittest.main()
