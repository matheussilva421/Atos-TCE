import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).parent
APP_ROOT = REPO_ROOT / "portable" / "app"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(APP_ROOT))

from analysis_pipeline import PipelineSummary, _write_json_atomic, run_local_pipeline
from batch_runner import _build_process_record, process_input_signature, run_manifest
from tce_extractor import Extraction, FieldEvidence


class BatchRunnerTests(unittest.TestCase):
    @staticmethod
    def _write_hash_manifest(root: Path, hashes: tuple[str, str]) -> Path:
        processes = []
        for index, (process, sha256) in enumerate(
            zip(("103439/2023", "103442/2023"), hashes), start=1
        ):
            pdf_path = root / f"document-{index}.pdf"
            pdf_path.write_bytes(b"placeholder")
            processes.append(
                {
                    "process": process,
                    "documents": [
                        {
                            "event": "9",
                            "title": "Resolução Administrativa",
                            "pdf_path": str(pdf_path),
                            "sha256": sha256,
                        }
                    ],
                }
            )
        path = root / "manifest.json"
        path.write_text(
            json.dumps({"version": 1, "run_id": "hash-run", "processes": processes}),
            encoding="utf-8",
        )
        return path

    def test_process_input_signature_is_independent_of_document_order(self):
        first = {
            "documents": [
                {"event": "12", "sha256": "bbb"},
                {"event": "9", "sha256": "aaa"},
            ]
        }
        reversed_documents = {"documents": list(reversed(first["documents"]))}

        self.assertEqual(
            process_input_signature(first),
            process_input_signature(reversed_documents),
        )

    def test_resume_reanalyzes_only_process_whose_hash_changed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = self._write_hash_manifest(root, ("aaa", "bbb"))
            output_path = root / "doc.md"
            checkpoint_path = root / "checkpoint.json"
            pages = ["RESOLUÇÃO ADMINISTRATIVA Nº 156\nInteressada: JOANA DA SILVA"]

            with patch("batch_runner.extract_pdf_pages", return_value=pages) as extract:
                run_manifest(manifest_path, output_path, checkpoint_path, run_id="hash-run")
                self._write_hash_manifest(root, ("aaa", "changed"))
                run_manifest(manifest_path, output_path, checkpoint_path, run_id="hash-run")

            self.assertEqual(
                [call.args[0].name for call in extract.call_args_list],
                ["document-1.pdf", "document-2.pdf", "document-2.pdf"],
            )

    def test_legacy_checkpoint_without_signature_reprocesses_exactly_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = self._write_hash_manifest(root, ("aaa", "bbb"))
            output_path = root / "doc.md"
            checkpoint_path = root / "checkpoint.json"
            pages = ["RESOLUÇÃO ADMINISTRATIVA Nº 156\nInteressada: JOANA DA SILVA"]

            with patch("batch_runner.extract_pdf_pages", return_value=pages) as extract:
                run_manifest(manifest_path, output_path, checkpoint_path, run_id="hash-run")
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                checkpoint["processes"]["103439/2023"].pop("input_signature", None)
                checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
                run_manifest(manifest_path, output_path, checkpoint_path, run_id="hash-run")
                run_manifest(manifest_path, output_path, checkpoint_path, run_id="hash-run")

            self.assertEqual(
                [call.args[0].name for call in extract.call_args_list].count("document-1.pdf"),
                2,
            )
            saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertIn("input_signature", saved["processes"]["103439/2023"])

    def test_run_local_pipeline_composes_all_stages_and_returns_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stage_order = []
            index = {"version": 1, "processes": []}
            classified = {"version": 1, "processes": []}
            manifest = {
                "version": 1,
                "processes": [{"process": "103439/2023", "documents": []}],
            }

            def stage(name, result=None):
                def invoke(*args, **kwargs):
                    stage_order.append(name)
                    return result

                return invoke

            def fake_extraction(manifest_path, output_path, checkpoint_path, **kwargs):
                stage_order.append("extraction")
                Path(checkpoint_path).write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "run_id": "pipeline-run",
                            "processes": {
                                "103439/2023": {
                                    "status": "partial",
                                    "result": {"status": "partial", "blocks": []},
                                }
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return {"total": 1, "completed": 0, "partial": 1}

            with (
                patch(
                    "analysis_pipeline.write_index", side_effect=stage("index", index)
                ) as write_index,
                patch(
                    "analysis_pipeline.classify_archive",
                    side_effect=stage("classification", classified),
                ) as classify,
                patch(
                    "analysis_pipeline.build_target_manifest",
                    side_effect=stage("manifest", manifest),
                ) as build,
                patch(
                    "analysis_pipeline.run_manifest",
                    side_effect=fake_extraction,
                ) as extract,
                patch(
                    "analysis_pipeline.write_html", side_effect=stage("html")
                ) as write_html,
                patch(
                    "analysis_pipeline.export_extension_dataset",
                    side_effect=stage("extension"),
                ) as export,
            ):
                summary = run_local_pipeline(
                    root,
                    tesseract=root / "runtime" / "tesseract.exe",
                    tessdata=root / "runtime" / "tessdata",
                    run_id="pipeline-run",
                )

            self.assertIsInstance(summary, PipelineSummary)
            self.assertEqual(summary.total_processes, 1)
            self.assertEqual(summary.priority_documents, 0)
            self.assertEqual(
                summary.extension_data_path,
                root / "dados-complementar-ato.json",
            )
            self.assertEqual(
                stage_order,
                [
                    "index",
                    "classification",
                    "manifest",
                    "extraction",
                    "html",
                    "extension",
                ],
            )
            write_index.assert_called_once_with(root, root / "indice-local.json")
            classify.assert_called_once_with(
                index,
                root / "cache-ocr.json",
                root / "runtime" / "tesseract.exe",
                root / "runtime" / "tessdata",
            )
            build.assert_called_once_with(classified)
            extract.assert_called_once_with(
                root / "pdfs-alvo-manifest.json",
                root / "doc.md",
                root / "checkpoint-extracao.json",
                run_id="pipeline-run",
                resume=True,
                tesseract=str(root / "runtime" / "tesseract.exe"),
                tessdata_dir=root / "runtime" / "tessdata",
            )
            write_html.assert_called_once_with(
                root / "pdfs-alvo-manifest.json",
                root / "checkpoint-extracao.json",
                root / "complementar-ato.html",
                pdf_link_root=None,
                archive_index_path=root / "indice-classificado.json",
            )
            export.assert_called_once_with(
                root / "checkpoint-extracao.json",
                root / "dados-complementar-ato.json",
            )
            self.assertEqual(
                json.loads((root / "pdfs-alvo-manifest.json").read_text(encoding="utf-8")),
                manifest,
            )
            self.assertEqual(
                json.loads(
                    (root / "indice-classificado.json").read_text(encoding="utf-8")
                ),
                classified,
            )

    def test_atomic_manifest_write_cleans_temporary_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "pdfs-alvo-manifest.json"
            destination.write_text('{"state":"previous"}\n', encoding="utf-8")

            with patch(
                "analysis_pipeline.os.replace", side_effect=OSError("replace failed")
            ) as replace:
                with self.assertRaisesRegex(OSError, "replace failed"):
                    _write_json_atomic(destination, {"state": "new"})

            temporary_path, replaced_path = replace.call_args.args
            self.assertEqual(replaced_path, destination)
            self.assertFalse(Path(temporary_path).exists())
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                '{"state":"previous"}\n',
            )
            self.assertEqual(list(root.glob(".pdfs-alvo-manifest.json.*.tmp")), [])

    def test_missing_block_receives_process_resolution_date_without_guessing_between_dates(self):
        missing = {"data_publicacao_doe": FieldEvidence("data_publicacao_doe", None, "missing")}
        resolution = Extraction(
            process="103484/2023",
            event="6",
            document="resolucao.pdf",
            fields={
                "data_publicacao_doe": FieldEvidence(
                    "data_publicacao_doe", "29/05/2019", "found",
                    process="103484/2023", event="6", document="resolucao.pdf", page=1,
                )
            },
            interested="THEMES NADJA MARTINS MEDEIROS BARBOSA",
            kind="resolucao_administrativa",
        )
        guide = Extraction(
            process="103484/2023",
            event="9",
            document="guia.pdf",
            fields=missing,
            interested="THEMES NADJA MARTINS M BARBOSA",
            kind="guia_financeira_taxacao",
        )

        record = _build_process_record("103484/2023", [resolution, guide], [])

        guide_block = next(block for block in record["blocks"] if block["interested"].endswith("M BARBOSA"))
        publication = guide_block["fields"]["data_publicacao_doe"]
        self.assertEqual(publication.value, "29/05/2019")
        self.assertEqual(publication.citation, "Processo 103484/2023 · Evento 6 · p. 1")

    def test_missing_block_preserves_conflict_between_process_resolution_dates(self):
        def resolution(event, value, interested):
            return Extraction(
                process="103767/2023",
                event=event,
                document=f"resolucao-{event}.pdf",
                fields={
                    "data_publicacao_doe": FieldEvidence(
                        "data_publicacao_doe", value, "found",
                        process="103767/2023", event=event,
                        document=f"resolucao-{event}.pdf", page=1,
                    )
                },
                interested=interested,
                kind="resolucao_administrativa",
            )

        guide = Extraction(
            process="103767/2023", event="3", document="guia.pdf",
            fields={"data_publicacao_doe": FieldEvidence("data_publicacao_doe", None, "missing")},
            interested="SEVERINA MARIA DE MELO SILVA", kind="guia_financeira_taxacao",
        )
        record = _build_process_record(
            "103767/2023",
            [
                resolution("10", "20/10/2022", "SEVERINA MARIA DE SILVA"),
                resolution("12", "25/05/2017", None),
                guide,
            ],
            [],
        )

        guide_block = next(block for block in record["blocks"] if block["interested"].endswith("MELO SILVA"))
        publication = guide_block["fields"]["data_publicacao_doe"]
        self.assertEqual(publication.status, "conflict")
        self.assertEqual(
            [candidate.value for candidate in publication.candidates],
            ["20/10/2022", "25/05/2017"],
        )

    def test_resolution_complete_cargo_takes_priority_over_guide_abbreviation(self):
        resolution = Extraction(
            process="103785/2023", event="16", document="resolucao.pdf",
            fields={
                "cargo": FieldEvidence(
                    "cargo", 'PROFESSOR PN - IV, Classe "J"', "found",
                    process="103785/2023", event="16", document="resolucao.pdf", page=1,
                )
            },
            interested="ARLETE OLIVEIRA DO NASCIMENTO",
            kind="resolucao_administrativa",
        )
        guide = Extraction(
            process="103785/2023", event="12", document="guia.pdf",
            fields={
                "cargo": FieldEvidence(
                    "cargo", "PROF PERM NIVEL - IV", "found",
                    process="103785/2023", event="12", document="guia.pdf", page=1,
                )
            },
            interested="ARLETE OLIVEIRA DO NASCIMENTO",
            kind="guia_financeira_taxacao",
        )

        record = _build_process_record("103785/2023", [guide, resolution], [])

        cargo = record["blocks"][0]["fields"]["cargo"]
        self.assertEqual(cargo.status, "found")
        self.assertEqual(cargo.value, 'PROFESSOR PN - IV, Classe "J"')
        self.assertEqual(cargo.event, "16")

    def test_resolution_registration_takes_priority_over_guide_variant(self):
        resolution = Extraction(
            process="103439/2023", event="9", document="resolucao.pdf",
            fields={
                "matricula": FieldEvidence(
                    "matricula", "103.870-2/1", "found",
                    process="103439/2023", event="9", document="resolucao.pdf", page=1,
                )
            },
            interested="MAGNOLIA RAMALHO MACIEL PINTO LOPES",
            kind="resolucao_administrativa",
        )
        guide = Extraction(
            process="103439/2023", event="11", document="guia.pdf",
            fields={
                "matricula": FieldEvidence(
                    "matricula", "1038702.1", "found",
                    process="103439/2023", event="11", document="guia.pdf", page=1,
                )
            },
            interested="MAGNOLIA RAMALHO MACIEL PINTO LOPES",
            kind="guia_financeira_taxacao",
        )

        record = _build_process_record("103439/2023", [guide, resolution], [])

        registration = record["blocks"][0]["fields"]["matricula"]
        self.assertEqual(registration.status, "found")
        self.assertEqual(registration.value, "103.870-2/1")
        self.assertEqual(registration.event, "9")

    def test_explicit_republication_supersedes_original_resolution(self):
        original = Extraction(
            process="103494/2023", event="7", document="original.pdf",
            fields={
                "cargo": FieldEvidence(
                    "cargo", 'PROFESSOR PN - III, Classe "J"', "found",
                    process="103494/2023", event="7", document="original.pdf", page=1,
                )
            },
            interested="EVALDO BERNARDO FERREIRA",
            kind="resolucao_administrativa",
        )
        corrected = Extraction(
            process="103494/2023", event="9", document="republicada.pdf",
            fields={
                "cargo": FieldEvidence(
                    "cargo", 'PROFESSOR PN - IV, Classe "J"', "found",
                    process="103494/2023", event="9", document="republicada.pdf", page=1,
                )
            },
            interested="EVALDO BERNARDO FERREIRA",
            kind="resolucao_administrativa",
            is_republication=True,
        )

        record = _build_process_record("103494/2023", [original, corrected], [])

        cargo = record["blocks"][0]["fields"]["cargo"]
        self.assertEqual(cargo.status, "found")
        self.assertEqual(cargo.value, 'PROFESSOR PN - IV, Classe "J"')
        self.assertEqual(cargo.event, "9")

    def test_analysis_script_uses_the_selective_collection_manifest(self):
        script = (Path(__file__).parent / "analisar-organizados.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("pdfs-alvo-manifest.json", script)
        self.assertNotIn("$manifest = Join-Path $Root 'manifest.json'", script)

    def test_processes_manifest_writes_outputs_and_resumes_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "resolucao-103439.pdf"
            pdf_path.write_bytes(b"placeholder")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "run_id": "run-1",
                        "processes": [
                            {
                                "process": "103439/2023",
                                "documents": [
                                    {
                                        "event": "9",
                                        "date": "28/04/2023",
                                        "title": "Documento_Processo_Portal_Gestor",
                                        "pdf_path": str(pdf_path),
                                    }
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = root / "doc.md"
            checkpoint_path = root / "checkpoint.json"
            pages = [
                "RESOLUÇÃO ADMINISTRATIVA Nº 156, DE 20 DE FEVEREIRO DE 2020\n"
                "Interessada: JOANA DA SILVA\n"
                "Modalidade: aposentadoria voluntária\n"
                "Fundamento Legal: artigo 40 da Constituição Federal\n"
                "Publicação no Diário Oficial do Estado: 20/02/2020\n"
                "Cargo: PROFESSOR\n"
                "Matrícula nº 12345\n"
                "Data de Nascimento: 14/08/1965\n"
                "Gênero: Feminino"
            ]

            with patch("batch_runner.extract_pdf_pages", return_value=pages) as extract:
                first = run_manifest(
                    manifest_path,
                    output_path,
                    checkpoint_path,
                    run_id="run-1",
                    resume=True,
                )
                second = run_manifest(
                    manifest_path,
                    output_path,
                    checkpoint_path,
                    run_id="run-1",
                    resume=True,
                )

            self.assertEqual(first["completed"], 1)
            self.assertEqual(second["completed"], 1)
            self.assertEqual(extract.call_count, 1)
            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("## Processo 103439/2023", markdown)
            self.assertIn("### Interessado: JOANA DA SILVA", markdown)
            self.assertIn("Processo 103439/2023 · Evento 9 · p. 1", markdown)
            saved = checkpoint_path.read_text(encoding="utf-8")
            self.assertNotIn("qsIdProcesso", saved)
            self.assertNotIn("idSessao", saved)
            payload = json.loads(saved)
            self.assertEqual(payload["processes"]["103439/2023"]["status"], "complete")

    def test_resumes_saved_partial_process_without_reextracting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "resolucao-103439.pdf"
            pdf_path.write_bytes(b"placeholder")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "run_id": "run-partial",
                        "processes": [
                            {
                                "process": "103439/2023",
                                "documents": [
                                    {
                                        "event": "9",
                                        "date": "28/04/2023",
                                        "title": "Documento_Processo_Portal_Gestor",
                                        "pdf_path": str(pdf_path),
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_path = root / "doc.md"
            checkpoint_path = root / "checkpoint.json"
            pages = [
                "RESOLUÇÃO ADMINISTRATIVA Nº 156\n"
                "RESOLVE conceder aposentadoria voluntária a JOANA DA SILVA, "
                "no cargo de PROFESSOR, matrícula nº 12345."
            ]

            with patch("batch_runner.extract_pdf_pages", return_value=pages) as extract:
                first = run_manifest(
                    manifest_path,
                    output_path,
                    checkpoint_path,
                    run_id="run-partial",
                    resume=True,
                )
                second = run_manifest(
                    manifest_path,
                    output_path,
                    checkpoint_path,
                    run_id="run-partial",
                    resume=True,
                )

            self.assertEqual(first["partial"], 1)
            self.assertEqual(second["partial"], 1)
            self.assertEqual(extract.call_count, 1)
            self.assertIn("Status: parcial", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
