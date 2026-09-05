import json
import tempfile
import threading
import unittest
from pathlib import Path

import fitz

from probe_target_url import main as probe_main
from targeted_collection import collect_target_documents, identify_target_document, main


def make_pdf(text: str = "", *, metadata_title: str = "") -> bytes:
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    if metadata_title:
        document.set_metadata({"title": metadata_title})
    payload = document.tobytes()
    document.close()
    return payload


class TargetIdentificationTests(unittest.TestCase):
    def test_event_one_is_never_a_collection_target(self):
        result = identify_target_document(
            event="1",
            title="RESOLUÇÃO ADMINISTRATIVA",
            pdf_bytes=make_pdf("RESOLUÇÃO ADMINISTRATIVA Nº 10"),
        )

        self.assertEqual(result.status, "skipped_event")
        self.assertIsNone(result.kind)

    def test_identifies_targets_by_visible_title_or_native_pdf_content(self):
        by_title = identify_target_document(
            event="2",
            title="Guia Financeira / Taxação de Proventos",
            pdf_bytes=make_pdf(),
        )
        by_content = identify_target_document(
            event="9",
            title="Documento_Processo_Portal_Gest...",
            pdf_bytes=make_pdf(
                "RESOLUÇÃO ADMINISTRATIVA Nº 156\nConcede aposentadoria voluntária"
            ),
        )

        self.assertEqual(by_title.kind, "guia_financeira_taxacao")
        self.assertEqual(by_content.kind, "resolucao_administrativa")
        self.assertEqual(by_content.status, "target")

    def test_rejects_unrelated_administrative_document(self):
        result = identify_target_document(
            event="4",
            title="Informação Administrativa",
            pdf_bytes=make_pdf("Encaminhamento administrativo de aposentadoria ao setor"),
        )

        self.assertEqual(result.status, "unrelated")
        self.assertIsNone(result.kind)

    def test_scanned_generic_pdf_is_pending_without_ocr(self):
        result = identify_target_document(
            event="6",
            title="Documento_Processo_Portal_Gest...",
            pdf_bytes=make_pdf(),
        )

        self.assertEqual(result.status, "pending_no_native_text")
        self.assertIsNone(result.kind)


class TargetCollectionTests(unittest.TestCase):
    def test_documents_from_one_process_are_probed_concurrently(self):
        barrier = threading.Barrier(2, timeout=2)
        unrelated = make_pdf("Ofício de encaminhamento ao setor")

        def synchronized_downloader(_url: str) -> bytes:
            barrier.wait()
            return unrelated

        manifest = {
            "processes": [
                {
                    "process": "103439/2023",
                    "documents": [
                        {"event": "2", "title": "Documento", "url": "memory://2"},
                        {"event": "3", "title": "Documento", "url": "memory://3"},
                    ],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary = collect_target_documents(
                manifest,
                output_dir=root / "targets",
                checkpoint_path=root / "checkpoint.json",
                target_manifest_path=root / "targets.json",
                downloader=synchronized_downloader,
            )

        self.assertEqual(summary["documents_probed"], 2)
        self.assertEqual(summary["errors"], 0)

    def test_probe_cli_classifies_one_url_without_persisting_the_pdf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.pdf"
            source.write_bytes(make_pdf("GUIA FINANCEIRA - TAXAÇÃO DE PROVENTOS\nCOMPOSIÇÃO DA REMUNERAÇÃO"))

            result = probe_main(
                [
                    "--url",
                    source.as_uri(),
                    "--event",
                    "12",
                    "--title",
                    "Documento_Processo_Portal_Gest...",
                ]
            )

            self.assertEqual(result["status"], "target")
            self.assertEqual(result["kind"], "guia_financeira_taxacao")
            self.assertFalse(any(root.glob("*.tmp")))

    def test_persists_only_targets_and_removes_urls_from_checkpoint(self):
        resolution = make_pdf(
            "RESOLUÇÃO ADMINISTRATIVA Nº 156\nConcede aposentadoria voluntária"
        )
        guide = make_pdf("GUIA FINANCEIRA - TAXAÇÃO DE PROVENTOS")
        unrelated = make_pdf("Ofício de encaminhamento ao setor")
        payloads = {
            "memory://event-1": resolution,
            "memory://event-2": unrelated,
            "memory://event-9": resolution,
            "memory://event-12": guide,
        }
        manifest = {
            "processes": [
                {
                    "process": "103439/2023",
                    "documents": [
                        {"event": "1", "title": "RESOLUÇÃO ADMINISTRATIVA", "url": "memory://event-1"},
                        {"event": "2", "title": "Documento_Processo_Portal_Gest...", "url": "memory://event-2"},
                        {"event": "9", "title": "Documento_Processo_Portal_Gest...", "url": "memory://event-9"},
                        {"event": "12", "title": "Guia Financeira", "url": "memory://event-12"},
                    ],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint = root / "checkpoint.json"
            target_manifest = root / "targets.json"
            summary = collect_target_documents(
                manifest,
                output_dir=root / "targets",
                checkpoint_path=checkpoint,
                target_manifest_path=target_manifest,
                downloader=payloads.__getitem__,
            )

            saved = sorted((root / "targets").rglob("*.pdf"))
            checkpoint_text = checkpoint.read_text(encoding="utf-8")
            target_payload = json.loads(target_manifest.read_text(encoding="utf-8"))

        self.assertEqual(summary["targets_saved"], 2)
        self.assertEqual(len(saved), 2)
        self.assertNotIn("memory://", checkpoint_text)
        self.assertEqual(len(target_payload["processes"][0]["documents"]), 2)
        self.assertTrue(all(int(item["event"]) > 1 for item in target_payload["processes"][0]["documents"]))

    def test_cli_collects_from_a_url_manifest_without_ocr(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.pdf"
            source.write_bytes(make_pdf("GUIA FINANCEIRA - TAXAÇÃO DE PROVENTOS"))
            manifest = root / "pending.json"
            manifest.write_text(
                json.dumps(
                    {
                        "processes": [
                            {
                                "process": "103439/2023",
                                "documents": [
                                    {
                                        "event": "12",
                                        "title": "Documento_Processo_Portal_Gest...",
                                        "url": source.as_uri(),
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "--manifest",
                    str(manifest),
                    "--output-dir",
                    str(root / "targets"),
                    "--checkpoint",
                    str(root / "checkpoint.json"),
                    "--target-manifest",
                    str(root / "targets.json"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(list((root / "targets").rglob("*.pdf"))), 1)


if __name__ == "__main__":
    unittest.main()
