import json
import tempfile
import unittest
from pathlib import Path

from consolidate_results import consolidate_results


class ConsolidationTests(unittest.TestCase):
    def test_retry_replaces_error_and_outputs_ordered_url_free_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary = root / "primary"
            retry = root / "retry"
            pdf_root = root / "pdfs"
            primary.mkdir()
            retry.mkdir()

            process_map = root / "process-map.json"
            process_map.write_text(
                json.dumps(
                    {
                        "processes": [
                            {"process": "100001/2023", "id": 1},
                            {"process": "100002/2023", "id": 2},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            for process, filename in [
                ("100001-2023", "evento-0002-resolucao_administrativa.pdf"),
                ("100002-2023", "evento-0003-guia_financeira_taxacao.pdf"),
            ]:
                folder = pdf_root / process
                folder.mkdir(parents=True)
                (folder / filename).write_bytes(b"%PDF-1.4\n")

            (primary / "a.checkpoint.json").write_text(
                json.dumps(
                    {
                        "processes": [
                            {
                                "process": "100001/2023",
                                "documents": [
                                    {"event": "2", "card_id": "a", "status": "error"}
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (primary / "b.checkpoint.json").write_text(
                json.dumps(
                    {
                        "processes": [
                            {
                                "process": "100002/2023",
                                "documents": [
                                    {
                                        "event": "3",
                                        "card_id": "b",
                                        "status": "target",
                                        "kind": "guia_financeira_taxacao",
                                        "file": "evento-0003-guia_financeira_taxacao.pdf",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (retry / "a.checkpoint.json").write_text(
                json.dumps(
                    {
                        "processes": [
                            {
                                "process": "100001/2023",
                                "documents": [
                                    {
                                        "event": "2",
                                        "card_id": "a",
                                        "status": "target",
                                        "kind": "resolucao_administrativa",
                                        "file": "evento-0002-resolucao_administrativa.pdf",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = consolidate_results(
                process_map_path=process_map,
                primary_dir=primary,
                retry_dir=retry,
                pdf_root=pdf_root,
                checkpoint_out=root / "checkpoint.json",
                manifest_out=root / "manifest.json",
                summary_out=root / "summary.md",
            )

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            checkpoint_text = (root / "checkpoint.json").read_text(encoding="utf-8")

        self.assertEqual(result["targets_saved"], 2)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(
            [item["process"] for item in manifest["processes"]],
            ["100001/2023", "100002/2023"],
        )
        self.assertNotIn("url", checkpoint_text.casefold())


if __name__ == "__main__":
    unittest.main()
