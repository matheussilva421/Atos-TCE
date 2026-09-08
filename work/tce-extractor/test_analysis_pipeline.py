import json
import hashlib
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).parent
APP_ROOT = REPO_ROOT / "portable" / "app"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(APP_ROOT))

from analysis_pipeline import (
    EXTRACTOR_VERSION,
    OCR_VERSION,
    _write_json_atomic,
    build_target_manifest,
    classify_archive,
    run_local_pipeline,
    write_visual_evidence,
)
from archive_index import scan_archive
from html_generator import build_interface_payload, write_html


def doc(*, event: int, title: str, text: str, sha256: str | None = None) -> dict:
    path = Path(tempfile.gettempdir()) / f"analysis-{event}-{title.replace(' ', '-')}.pdf"
    return {
        "event": event,
        "title": title,
        "absolute_path": str(path),
        "relative_path": path.name,
        "sha256": sha256 or f"{event:064x}",
        "status": "complete",
        "_text": text,
    }


def make_index(documents: list[dict]) -> dict:
    return {"version": 1, "documents": documents}


class AnalysisPipelineTests(unittest.TestCase):
    def test_visual_evidence_sidecar_projects_manifest_documents_without_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            checkpoint = root / "checkpoint.json"
            sidecar = root / "evidencias-visuais.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "processes": [
                            {
                                "process": "103439/2023",
                                "documents": [
                                    {
                                        "event": "6",
                                        "event_id": "6",
                                        "id": "portal-doc-1",
                                        "title": "resolucao.pdf",
                                        "relative_path": "processos/103439-2023/resolucao.pdf",
                                        "sha256": "a" * 64,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            checkpoint.write_text(
                json.dumps(
                    {
                        "processes": {
                            "103439/2023": {
                                "result": {
                                    "process": "103439/2023",
                                    "blocks": [
                                        {
                                            "interested": "JOANA DA SILVA",
                                            "fields": {
                                                "cargo": {
                                                    "status": "found",
                                                    "value": "PROFESSOR",
                                                    "process": "103439/2023",
                                                    "event": "6",
                                                    "document": "resolucao.pdf",
                                                    "page": 1,
                                                    "quote": "PROFESSOR",
                                                    "rects": [[0.1, 0.2, 0.4, 0.3]],
                                                }
                                            },
                                        }
                                    ],
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            write_visual_evidence(manifest, checkpoint, sidecar)
            payload = json.loads(sidecar.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(len(payload["documents"]), 1)
        record_id = hashlib.sha256("103439/2023|joana da silva".encode()).hexdigest()
        self.assertEqual(payload["records"][record_id]["cargo"]["page"], 1)
        self.assertNotIn(str(root), json.dumps(payload))

    def test_local_pipeline_exports_extension_dataset_after_checkpoint_and_html(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index = {"version": 1, "processes": []}
            classified = {"version": 1, "processes": []}
            manifest = {
                "version": 1,
                "processes": [{"process": "103439/2023", "documents": []}],
            }

            def fake_run_manifest(manifest_path, markdown_path, checkpoint_path, **kwargs):
                Path(checkpoint_path).write_text(
                    json.dumps({"batch_id": "pipeline-run", "processes": {}}),
                    encoding="utf-8",
                )
                return {"total": 1, "completed": 0, "partial": 1}

            with (
                patch("analysis_pipeline.write_index", return_value=index),
                patch("analysis_pipeline.classify_archive", return_value=classified),
                patch("analysis_pipeline.build_target_manifest", return_value=manifest),
                patch("analysis_pipeline.run_manifest", side_effect=fake_run_manifest),
                patch("analysis_pipeline.write_html"),
            ):
                summary = run_local_pipeline(
                    root,
                    tesseract=root / "runtime" / "tesseract.exe",
                    tessdata=root / "runtime" / "tessdata",
                    run_id="pipeline-run",
                )

            expected_path = root / "dados-complementar-ato.json"
            self.assertTrue(expected_path.is_file())
            self.assertEqual(summary.extension_data_path, expected_path)
            self.assertEqual(
                json.loads(expected_path.read_text(encoding="utf-8"))["batch"]["id"],
                "pipeline-run",
            )

    def test_local_pipeline_html_uses_the_same_encoded_archive_link_for_priority_and_all_documents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            relative_path = (
                "processos/103439-2023/evento-0009/ato final nº 1 (v1).pdf"
            )
            pdf = root / relative_path
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.7 fixture")
            index = {"version": 1, "processes": []}
            classified = {
                "version": 1,
                "processes": [
                    {
                        "key": "103439/2023",
                        "events": [
                            {
                                "event": 9,
                                "documents": [
                                    {
                                        "title": "RESOLUÇÃO ADMINISTRATIVA",
                                        "relative_path": relative_path,
                                        "classification": "resolucao_administrativa",
                                        "automatic_source": True,
                                        "status": "complete",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
            manifest = {
                "version": 1,
                "processes": [
                    {
                        "process": "103439/2023",
                        "documents": [
                            {
                                "event": "9",
                                "title": "RESOLUÇÃO ADMINISTRATIVA",
                                "classification": "resolucao_administrativa",
                                "automatic_source": True,
                                "relative_path": relative_path,
                                "pdf_path": str(pdf),
                            }
                        ],
                    }
                ],
            }

            def fake_run_manifest(manifest_path, markdown_path, checkpoint_path, **kwargs):
                Path(checkpoint_path).write_text(
                    json.dumps(
                        {
                            "batch_id": "pipeline-run",
                            "processes": {
                                "103439/2023": {
                                    "status": "partial",
                                    "documents": [
                                        {
                                            "event": "9",
                                            "file": pdf.name,
                                            "pages": 1,
                                            "classification": "resolucao_administrativa",
                                        }
                                    ],
                                    "result": {"blocks": []},
                                }
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return {"total": 1, "completed": 0, "partial": 1}

            with (
                patch("analysis_pipeline.write_index", return_value=index),
                patch("analysis_pipeline.classify_archive", return_value=classified),
                patch("analysis_pipeline.build_target_manifest", return_value=manifest),
                patch("analysis_pipeline.run_manifest", side_effect=fake_run_manifest),
                patch("analysis_pipeline.export_extension_dataset"),
            ):
                summary = run_local_pipeline(
                    root,
                    tesseract=root / "runtime" / "tesseract.exe",
                    tessdata=root / "runtime" / "tessdata",
                    run_id="pipeline-run",
                )

            expected_url = (
                "processos/103439-2023/evento-0009/ato%20final%20n%C2%BA%201%20(v1).pdf"
            )
            payload = build_interface_payload(
                root / "pdfs-alvo-manifest.json",
                root / "checkpoint-extracao.json",
                archive_index_path=root / "indice-classificado.json",
            )
            priority_url = payload["processes"][0]["documents"][0]["pdf_url"]
            all_documents_url = payload["processes"][0]["all_documents"][0]["pdf_url"]

            self.assertEqual(priority_url, expected_url)
            self.assertEqual(all_documents_url, expected_url)
            self.assertEqual(priority_url, all_documents_url)
            html = summary.html_path.read_text(encoding="utf-8")
            self.assertEqual(html.count(expected_url), 2)
            self.assertNotIn("file:", html)

    def test_cli_help_exposes_archive_and_runtime_paths(self):
        result = subprocess.run(
            [sys.executable, str(APP_ROOT / "analysis_pipeline.py"), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--archive-root", result.stdout)
        self.assertIn("--tesseract", result.stdout)
        self.assertIn("--tessdata", result.stdout)

    def test_classification_records_page_count_from_native_and_ocr_pages(self):
        native = doc(event=9, title="Resolução", text="native")
        scanned = doc(event=10, title="Documento", text="")

        with tempfile.TemporaryDirectory() as temporary:
            classified = classify_archive(
                make_index([native, scanned]),
                cache_path=Path(temporary) / "cache.json",
                text_reader=lambda path: (
                    ["RESOLUÇÃO ADMINISTRATIVA página 1", "continuação página 2"]
                    if path.name == Path(native["absolute_path"]).name
                    else []
                ),
                ocr_reader=lambda path: [
                    "GUIA FINANCEIRA TAXAÇÃO página 1",
                    "continuação página 2",
                    "continuação página 3",
                ],
            )

        self.assertEqual(
            [item["page_count"] for item in classified["documents"]], [2, 3]
        )

    def test_real_scan_classify_and_html_preserve_document_review_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "acervo-tce"
            process_dir = archive / "processos" / "103439-2023"
            records = [
                (9, "resolucao.pdf", "RESOLUÇÃO ADMINISTRATIVA"),
                (10, "conflito.pdf", "RESOLUÇÃO ADMINISTRATIVA"),
                (11, "pendente.pdf", "Documento digitalizado"),
            ]
            events = []
            for event_number, filename, title in records:
                event_dir = process_dir / f"evento-{event_number:04d}"
                event_dir.mkdir(parents=True)
                pdf = event_dir / filename
                pdf.write_bytes(b"%PDF-1.7 fixture")
                event = {
                    "event": event_number,
                    "event_id": event_number,
                    "title": f"Evento {event_number}",
                    "documents": [
                        {
                            "id": f"doc-{event_number}",
                            "title": title,
                            "path": pdf.relative_to(archive).as_posix(),
                            "status": "complete",
                        }
                    ],
                }
                (event_dir / "evento.json").write_text(
                    json.dumps(event), encoding="utf-8"
                )
                events.append(event)
            process_dir.mkdir(parents=True, exist_ok=True)
            (process_dir / "processo.json").write_text(
                json.dumps({"key": "103439/2023", "events": events}),
                encoding="utf-8",
            )

            raw_index = scan_archive(archive)
            classified = classify_archive(
                raw_index,
                cache_path=archive / "cache-ocr.json",
                text_reader=lambda path: (
                    ["RESOLUÇÃO ADMINISTRATIVA página 1", "continuação página 2"]
                    if path.name == "resolucao.pdf"
                    else ["GUIA FINANCEIRA TAXAÇÃO"]
                    if path.name == "conflito.pdf"
                    else []
                ),
                ocr_reader=lambda path: [],
            )
            classified_path = archive / "indice-classificado.json"
            _write_json_atomic(classified_path, classified)
            manifest_payload = build_target_manifest(classified)
            manifest = archive / "pdfs-alvo-manifest.json"
            _write_json_atomic(manifest, manifest_payload)
            checkpoint = archive / "checkpoint-extracao.json"
            checkpoint.write_text(
                json.dumps({"processes": {"103439/2023": {"status": "partial"}}}),
                encoding="utf-8",
            )
            output = archive / "fixture.html"

            write_html(
                manifest,
                checkpoint,
                output,
                archive_index_path=classified_path,
            )
            payload = build_interface_payload(
                manifest, checkpoint, archive_index_path=classified_path
            )

            documents = payload["processes"][0]["all_documents"]
            self.assertEqual(
                [item["classification"] for item in documents],
                ["resolucao_administrativa", "outro_documento", "pendente_ocr"],
            )
            self.assertEqual([item["page_count"] for item in documents], [2, 1, 0])
            self.assertTrue(documents[1]["classification_conflict"])
            self.assertTrue(documents[2]["pending"])
            html = output.read_text(encoding="utf-8")
            self.assertIn("badge-resolution", html)
            self.assertIn("badge-conflict", html)
            self.assertIn("badge-pending", html)

    def test_classifies_title_content_and_never_targets_event_one(self):
        documents = [
            doc(event=1, title="RESOLUÇÃO ADMINISTRATIVA", text="RESOLUÇÃO"),
            doc(event=9, title="Documento", text="RESOLUÇÃO ADMINISTRATIVA Nº 156"),
            doc(event=12, title="Guia Financeira", text="GUIA FINANCEIRA - TAXAÇÃO"),
            doc(event=13, title="Ofício", text="Encaminhamento"),
        ]

        def fake_reader(path: Path) -> list[str]:
            return next(item["_text"] for item in documents if item["absolute_path"] == str(path)).split("\n")

        with tempfile.TemporaryDirectory() as temporary:
            classified = classify_archive(
                make_index(documents),
                cache_path=Path(temporary) / "cache.json",
                text_reader=fake_reader,
                ocr_reader=lambda path: [],
            )

        self.assertEqual(
            [item["classification"] for item in classified["documents"]],
            [
                "outro_documento",
                "resolucao_administrativa",
                "guia_financeira_taxacao",
                "outro_documento",
            ],
        )
        self.assertFalse(classified["documents"][0]["automatic_source"])

    def test_conflicting_title_metadata_and_content_signals_never_target(self):
        documents = [
            doc(
                event=9,
                title="RESOLUÇÃO ADMINISTRATIVA",
                text="RESOLUÇÃO ADMINISTRATIVA Nº 156\nRESOLVE conceder",
            )
        ]
        documents[0]["metadata_title"] = "Guia Financeira - Taxação de Proventos"

        with tempfile.TemporaryDirectory() as temporary:
            classified = classify_archive(
                make_index(documents),
                cache_path=Path(temporary) / "cache.json",
                text_reader=lambda path: [documents[0]["_text"]],
                ocr_reader=lambda path: [],
            )

        record = classified["documents"][0]
        self.assertEqual(record["classification"], "outro_documento")
        self.assertFalse(record["automatic_source"])
        self.assertTrue(record["classification_conflict"])
        self.assertEqual(
            {signal["classification"] for signal in record["classification_signals"]},
            {"resolucao_administrativa", "guia_financeira_taxacao"},
        )

    def test_default_ocr_requires_explicit_existing_tesseract_and_tessdata(self):
        documents = [doc(event=9, title="Documento", text="")]

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                classify_archive(
                    make_index(documents),
                    cache_path=Path(temporary) / "cache.json",
                    text_reader=lambda path: [],
                )

    def test_component_change_invalidates_cached_ocr_pages(self):
        documents = [doc(event=9, title="Documento", text="", sha256="e" * 64)]
        calls = {"ocr": 0}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tesseract = root / "tesseract.exe"
            tessdata = root / "tessdata"
            tessdata.mkdir()
            tesseract.write_bytes(b"tesseract-v1")
            (tessdata / "por.traineddata").write_bytes(b"por-v1")
            (tessdata / "eng.traineddata").write_bytes(b"eng-v1")
            cache_path = root / "cache.json"

            def fake_ocr(path: Path) -> list[str]:
                calls["ocr"] += 1
                return ["RESOLUÇÃO ADMINISTRATIVA Nº 156"]

            for _ in range(2):
                classify_archive(
                    make_index(documents),
                    cache_path=cache_path,
                    tesseract=tesseract,
                    tessdata=tessdata,
                    text_reader=lambda path: [],
                    ocr_reader=fake_ocr,
                )

            saved = json.loads(cache_path.read_text(encoding="utf-8"))
            runtime_identity = saved["runtime_identity"]
            self.assertIn(
                f"{documents[0]['sha256']}:{runtime_identity}",
                saved["entries"],
            )

            tesseract.write_bytes(b"tesseract-v2")
            classify_archive(
                make_index(documents),
                cache_path=cache_path,
                tesseract=tesseract,
                tessdata=tessdata,
                text_reader=lambda path: [],
                ocr_reader=fake_ocr,
            )
            (tessdata / "por.traineddata").write_bytes(b"por-v2")
            classify_archive(
                make_index(documents),
                cache_path=cache_path,
                tesseract=tesseract,
                tessdata=tessdata,
                text_reader=lambda path: [],
                ocr_reader=fake_ocr,
            )

        self.assertEqual(calls["ocr"], 3)

    def test_relative_ocr_paths_are_resolved_and_subprocess_gets_absolute_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "blank.pdf"
            try:
                import fitz
            except ImportError:  # pragma: no cover - environment guard
                self.skipTest("fitz não disponível")
            pdf = fitz.open()
            pdf.new_page()
            pdf.save(pdf_path)
            pdf.close()

            tesseract = root / "bin" / "tesseract.exe"
            tessdata = root / "tessdata"
            tesseract.parent.mkdir()
            tessdata.mkdir()
            tesseract.write_bytes(b"tesseract")
            (tessdata / "por.traineddata").write_bytes(b"por")
            (tessdata / "eng.traineddata").write_bytes(b"eng")
            relative_tesseract = os.path.relpath(tesseract, Path.cwd())
            relative_tessdata = os.path.relpath(tessdata, Path.cwd())
            document = doc(event=9, title="Documento", text="", sha256="f" * 64)
            document["absolute_path"] = str(pdf_path)

            with patch(
                "analysis_pipeline.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=b"", stderr=b""
                ),
            ) as run:
                classify_archive(
                    make_index([document]),
                    cache_path=root / "cache.json",
                    tesseract=relative_tesseract,
                    tessdata=relative_tessdata,
                )

        command = run.call_args.args[0]
        self.assertEqual(command[0], str(tesseract.resolve()))
        self.assertTrue(Path(command[0]).is_absolute())
        self.assertEqual(command[command.index("--tessdata-dir") + 1], str(tessdata.resolve()))

    def test_priority_signal_in_mixed_non_target_title_prevents_exclusion_guard(self):
        documents = [
            doc(
                event=9,
                title="Ofício — Resolução Administrativa",
                text="12345\n---",
                sha256="1" * 64,
            )
        ]
        calls = {"ocr": 0}

        def fake_ocr(path: Path) -> list[str]:
            calls["ocr"] += 1
            return ["RESOLUÇÃO ADMINISTRATIVA Nº 156"]

        with tempfile.TemporaryDirectory() as temporary:
            classified = classify_archive(
                make_index(documents),
                cache_path=Path(temporary) / "cache.json",
                text_reader=lambda path: ["12345", "---"],
                ocr_reader=fake_ocr,
            )

        self.assertEqual(calls["ocr"], 1)
        self.assertEqual(
            classified["documents"][0]["classification"],
            "resolucao_administrativa",
        )

    def test_short_native_numbering_and_noise_do_not_suppress_ocr(self):
        documents = [doc(event=9, title="Documento", text="12345\n---")]
        calls = {"ocr": 0}

        def fake_ocr(path: Path) -> list[str]:
            calls["ocr"] += 1
            return ["RESOLUÇÃO ADMINISTRATIVA Nº 156"]

        with tempfile.TemporaryDirectory() as temporary:
            classified = classify_archive(
                make_index(documents),
                cache_path=Path(temporary) / "cache.json",
                text_reader=lambda path: ["12345", "---"],
                ocr_reader=fake_ocr,
            )

        self.assertEqual(calls["ocr"], 1)
        self.assertEqual(
            classified["documents"][0]["classification"],
            "resolucao_administrativa",
        )

    def test_event_zero_and_invalid_event_never_read_as_automatic_sources(self):
        documents = [
            doc(event=0, title="RESOLUÇÃO ADMINISTRATIVA", text="RESOLVE"),
            doc(event=0, title="RESOLUÇÃO ADMINISTRATIVA", text="RESOLVE"),
        ]
        documents[1]["event"] = "evento-inválido"
        reads = {"native": 0, "ocr": 0}

        def reader(path: Path) -> list[str]:
            reads["native"] += 1
            return ["RESOLUÇÃO ADMINISTRATIVA Nº 1"]

        def ocr(path: Path) -> list[str]:
            reads["ocr"] += 1
            return ["RESOLUÇÃO ADMINISTRATIVA Nº 1"]

        with tempfile.TemporaryDirectory() as temporary:
            classified = classify_archive(
                make_index(documents),
                cache_path=Path(temporary) / "cache.json",
                text_reader=reader,
                ocr_reader=ocr,
            )

        self.assertEqual(
            [item["classification"] for item in classified["documents"]],
            ["outro_documento", "outro_documento"],
        )
        self.assertEqual(reads, {"native": 0, "ocr": 0})

    def test_empty_text_uses_ocr_once_and_invalidates_cache_by_versions(self):
        documents = [doc(event=9, title="Guia", text="", sha256="a" * 64)]
        calls = {"ocr": 0}

        def fake_reader(path: Path) -> list[str]:
            return []

        def fake_ocr(path: Path) -> list[str]:
            calls["ocr"] += 1
            return ["GUIA FINANCEIRA - TAXAÇÃO"]

        with tempfile.TemporaryDirectory() as temporary:
            cache_path = Path(temporary) / "cache.json"
            first = classify_archive(
                make_index(documents),
                cache_path=cache_path,
                text_reader=fake_reader,
                ocr_reader=fake_ocr,
            )
            second = classify_archive(
                make_index(documents),
                cache_path=cache_path,
                text_reader=fake_reader,
                ocr_reader=fake_ocr,
            )

            saved = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(calls["ocr"], 1)
            self.assertEqual(first["documents"][0]["classification"], "guia_financeira_taxacao")
            self.assertEqual(second["documents"][0]["text_source"], "ocr_cache")
            self.assertEqual(saved["extractor_version"], EXTRACTOR_VERSION)
            self.assertEqual(saved["ocr_version"], OCR_VERSION)

            saved["ocr_version"] = "older-ocr"
            cache_path.write_text(json.dumps(saved), encoding="utf-8")
            classify_archive(
                make_index(documents),
                cache_path=cache_path,
                text_reader=fake_reader,
                ocr_reader=fake_ocr,
            )

        self.assertEqual(calls["ocr"], 2)

    def test_geometry_cache_keeps_text_and_boxes_from_the_same_ocr_result(self):
        documents = [doc(event=9, title="Resolução", text="", sha256="d" * 64)]
        geometry = [
            {
                "page": 0,
                "method": "ocr",
                "coordinates": "normalized",
                "words": [{"text": "RESOLUÇÃO", "rect": [0.1, 0.1, 0.4, 0.2]}],
            }
        ]
        calls = {"ocr": 0}

        def fake_ocr(path: Path):
            calls["ocr"] += 1
            return (["RESOLUÇÃO ADMINISTRATIVA Nº 156"], geometry)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_path = root / "cache.json"
            geometry_path = root / "cache-geometria.json"
            first = classify_archive(
                make_index(documents),
                cache_path=cache_path,
                geometry_cache_path=geometry_path,
                text_reader=lambda path: [],
                ocr_reader=fake_ocr,
            )
            second = classify_archive(
                make_index(documents),
                cache_path=cache_path,
                geometry_cache_path=geometry_path,
                text_reader=lambda path: [],
                ocr_reader=lambda path: (_ for _ in ()).throw(AssertionError("OCR repetido")),
            )
            manifest = build_target_manifest(first)
            saved_geometry = json.loads(geometry_path.read_text(encoding="utf-8"))

        self.assertEqual(calls["ocr"], 1)
        self.assertEqual(first["documents"][0]["text_source"], "ocr_geometry")
        self.assertEqual(second["documents"][0]["text_source"], "ocr_geometry_cache")
        self.assertIn("geometry_cache_key", manifest["processes"][0]["documents"][0])
        self.assertEqual(saved_geometry["geometry_version"], 1)
        self.assertEqual(len(saved_geometry["entries"]), 1)

    def test_empty_or_failed_reading_is_not_an_automatic_target(self):
        empty = [doc(event=9, title="Documento", text="", sha256="b" * 64)]
        failed = [doc(event=9, title="Documento", text="native", sha256="c" * 64)]

        def empty_reader(path: Path) -> list[str]:
            return []

        def failed_reader(path: Path) -> list[str]:
            raise OSError("fixture read failed")

        with tempfile.TemporaryDirectory() as temporary:
            empty_result = classify_archive(
                make_index(empty),
                cache_path=Path(temporary) / "empty-cache.json",
                text_reader=empty_reader,
                ocr_reader=lambda path: [],
            )
            failed_result = classify_archive(
                make_index(failed),
                cache_path=Path(temporary) / "failed-cache.json",
                text_reader=failed_reader,
                ocr_reader=lambda path: ["RESOLUÇÃO ADMINISTRATIVA Nº 1"],
            )

        self.assertEqual(empty_result["documents"][0]["classification"], "pendente_ocr")
        self.assertFalse(empty_result["documents"][0]["automatic_source"])
        self.assertEqual(failed_result["documents"][0]["classification"], "erro_leitura")
        self.assertFalse(failed_result["documents"][0]["automatic_source"])

    def test_target_manifest_only_contains_post_event_one_automatic_targets(self):
        classified = {
            "version": 1,
            "processes": [
                {
                    "key": "103439/2023",
                    "events": [
                        {
                            "event": 1,
                            "documents": [
                                {
                                    "title": "RESOLUÇÃO ADMINISTRATIVA",
                                    "classification": "resolucao_administrativa",
                                    "automatic_source": False,
                                    "relative_path": "event-1.pdf",
                                }
                            ],
                        },
                        {
                            "event": 9,
                            "documents": [
                                {
                                    "title": "Resolução",
                                    "classification": "resolucao_administrativa",
                                    "automatic_source": True,
                                    "sha256": "d" * 64,
                                    "relative_path": "event-9.pdf",
                                    "absolute_path": "C:/archive/event-9.pdf",
                                },
                                {
                                    "title": "Despacho",
                                    "classification": "outro_documento",
                                    "automatic_source": False,
                                    "relative_path": "despacho.pdf",
                                },
                            ],
                        },
                    ],
                }
            ],
        }

        manifest = build_target_manifest(classified)

        self.assertEqual(manifest["processes"][0]["process"], "103439/2023")
        self.assertEqual(len(manifest["processes"][0]["documents"]), 1)
        self.assertEqual(manifest["processes"][0]["documents"][0]["event"], "9")
        self.assertEqual(manifest["processes"][0]["documents"][0]["pdf_path"], "C:/archive/event-9.pdf")


if __name__ == "__main__":
    unittest.main()
