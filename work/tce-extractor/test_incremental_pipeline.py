import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

APP_ROOT = Path(__file__).parent / "portable" / "app"
import sys
sys.path.insert(0, str(APP_ROOT))

from incremental_pipeline import analyze_process, current_results, publish_results  # noqa: E402


class IncrementalPipelineTests(unittest.TestCase):
    def test_analyze_process_classifies_only_requested_process_and_publishes_result(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = {
                "version": 1,
                "process_keys": ["1/2023", "2/2023"],
                "processes": [
                    {"key": "1/2023", "events": [{"event": "2", "documents": []}]},
                    {"key": "2/2023", "events": [{"event": "2", "documents": []}]},
                ],
            }
            classified = {
                "version": 1,
                "processes": [{"key": "1/2023", "events": []}],
            }
            manifest = {
                "version": 1,
                "processes": [{"process": "1/2023", "documents": []}],
            }

            def fake_run_manifest(manifest_path, output_path, checkpoint_path, **_kwargs):
                Path(checkpoint_path).write_text(
                    json.dumps(
                        {
                            "processes": {
                                "1/2023": {
                                    "result": {
                                        "process": "1/2023",
                                        "status": "partial",
                                        "blocks": [],
                                    }
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                return {"total": 1, "completed": 0, "partial": 1}

            with (
                patch("incremental_pipeline.scan_archive", return_value=index),
                patch("incremental_pipeline.classify_archive", return_value=classified) as classify,
                patch("incremental_pipeline.build_target_manifest", return_value=manifest) as build_manifest,
                patch("incremental_pipeline.run_manifest", side_effect=fake_run_manifest),
            ):
                result = analyze_process(root, "1/2023", tesseract="tesseract", tessdata="tessdata")

            selected_index = classify.call_args.args[0]
            self.assertEqual([item["key"] for item in selected_index["processes"]], ["1/2023"])
            self.assertEqual(build_manifest.call_count, 2)
            self.assertEqual(build_manifest.call_args_list[0].kwargs, {})
            self.assertEqual(build_manifest.call_args_list[1].kwargs["archive_root"], root)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(current_results(root)["1/2023"]["status"], "partial")

    def test_analyze_process_publishes_preparing_state_before_analysis(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = {"version": 1, "process_keys": ["1/2023"], "processes": [{"key": "1/2023"}]}
            classified = {"version": 1, "processes": [{"key": "1/2023", "events": []}]}
            manifest = {"version": 1, "processes": [{"process": "1/2023", "documents": []}]}
            observed = []

            def fake_publish(_root, results, **_kwargs):
                observed.append(dict(results))
                return len(observed)

            def fake_run_manifest(_manifest_path, _output_path, checkpoint_path, **_kwargs):
                Path(checkpoint_path).write_text(
                    json.dumps({"processes": {"1/2023": {"result": {"status": "partial", "blocks": []}}}}),
                    encoding="utf-8",
                )
                return {"total": 1, "completed": 0, "partial": 1}

            with (
                patch("incremental_pipeline.scan_archive", return_value=index),
                patch("incremental_pipeline.classify_archive", return_value=classified),
                patch("incremental_pipeline.build_target_manifest", return_value=manifest),
                patch("incremental_pipeline.run_manifest", side_effect=fake_run_manifest),
                patch("incremental_pipeline.publish_results", side_effect=fake_publish),
            ):
                analyze_process(root, "1/2023", tesseract="tesseract", tessdata="tessdata")

            self.assertEqual(observed[0]["1/2023"]["status"], "preparando")
            self.assertEqual(observed[-1]["1/2023"]["status"], "partial")

    def test_publication_keeps_unaffected_process(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            publish_results(root, {"1/2023": {"status": "partial"}})
            publish_results(root, {"2/2023": {"status": "partial"}})
            results = current_results(root)
            self.assertEqual(set(results), {"1/2023", "2/2023"})
            pointer = json.loads((root / "publicacao-atual.json").read_text(encoding="utf-8"))
            self.assertEqual(pointer["schema_version"], 1)
            self.assertEqual(pointer["revision"], 2)

    def test_publication_replaces_only_named_process_and_retains_previous_snapshot(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            publish_results(root, {"1/2023": {"status": "partial", "value": 1}})
            publish_results(root, {"1/2023": {"status": "complete", "value": 2}})
            self.assertEqual(current_results(root)["1/2023"]["value"], 2)
            revisions = sorted((root / "publicacoes").iterdir())
            self.assertEqual(len(revisions), 2)

    def test_publication_materializes_valid_extension_dataset_for_each_revision(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            publish_results(root, {"1/2023": {"status": "partial", "blocks": []}})
            dataset_path = root / "publicacoes" / "1" / "dataset.json"
            dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
            self.assertEqual(dataset["schema_version"], 1)
            self.assertEqual(dataset["batch"]["process_keys"], ["1/2023"])
            self.assertEqual(dataset["batch"]["record_count"], 0)

    def test_publication_materializes_safe_review_snapshot_for_incremental_revision(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {
                "version": 1,
                "processes": [{
                    "process": "1/2023",
                    "documents": [{
                        "event": "9",
                        "id": "doc-9",
                        "title": "RESOLUÇÃO",
                        "relative_path": "acervo-tce/processos/1-2023/evento-0009/resolucao.pdf",
                        "pdf_path": str(root / "acervo-tce" / "processos" / "1-2023" / "evento-0009" / "resolucao.pdf"),
                    }],
                }],
            }
            review_index = {
                "version": 1,
                "processes": [{
                    "key": "1/2023",
                    "events": [{
                        "event": "9",
                        "documents": [{
                            "id": "doc-9",
                            "title": "RESOLUÇÃO",
                            "relative_path": "acervo-tce/processos/1-2023/evento-0009/resolucao.pdf",
                        }],
                    }],
                }],
            }

            publish_results(
                root,
                {"1/2023": {"status": "partial", "blocks": []}},
                review_manifest=manifest,
                review_index=review_index,
            )

            review = json.loads(
                (root / "publicacoes" / "1" / "review-data.json").read_text(encoding="utf-8")
            )
            document = review["processes"][0]["documents"][0]
            self.assertEqual(review["live_revision"], 1)
            self.assertEqual(document["pdf_url"], "acervo-tce/processos/1-2023/evento-0009/resolucao.pdf")
            self.assertNotIn(str(root), json.dumps(review, ensure_ascii=False))

    def test_incremental_review_seeds_manifest_from_canonical_archive(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = {
                "version": 1,
                "processes": [
                    {"process": "1/2023", "documents": []},
                    {"process": "2/2023", "documents": []},
                ],
            }
            (root / "pdfs-alvo-manifest.json").write_text(
                json.dumps(canonical), encoding="utf-8"
            )
            (root / "colecoes-processos.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "default_collection": "sector_finalistic",
                        "collections": [
                            {"id": "my_processes", "label": "Meus Processos", "process_keys": ["1/2023"]},
                            {"id": "sector_finalistic", "label": "Processos no Setor", "process_keys": ["2/2023"]},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            publish_results(
                root,
                {
                    "1/2023": {"status": "partial", "blocks": []},
                    "2/2023": {"status": "partial", "blocks": []},
                },
                review_manifest={"version": 1, "processes": [{"process": "2/2023", "documents": []}]},
                review_index={"version": 1, "processes": []},
            )

            published = json.loads(
                (root / "publicacoes" / "1" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [item["process"] for item in published["processes"]],
                ["1/2023", "2/2023"],
            )


if __name__ == "__main__":
    unittest.main()
