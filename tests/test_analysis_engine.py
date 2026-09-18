"""Tests for the promoted analysis engine (M6 Task 1)."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.analysis import legacy_adapter
from app.analysis.engine import archive_index, incremental_pipeline

PDF = b"%PDF-1.4\nengine fixture\n%%EOF\n"


class PromotedEngineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.archive_root = Path(self._tmp.name) / "data" / "archive"
        folder = self.archive_root / "processos" / "102390-2026" / "evento-0001-7047389"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "documento-001-Ato.pdf").write_bytes(PDF)
        # The archive index is built from the per-process manifests, exactly as
        # the proven layout writes them.
        (folder / "evento.json").write_text(
            json.dumps({"event": 1, "event_id": "7047389", "date": "01/09/2026", "title": "DE - Ato", "active": True}),
            encoding="utf-8",
        )
        (self.archive_root / "processos" / "102390-2026" / "processo.json").write_text(
            json.dumps(
                {
                    "key": "102390/2026",
                    "id": "622888",
                    "number": "102390",
                    "year": 2026,
                    "status": "complete",
                    "synced_at": "2026-09-15T01:08:30Z",
                    "events": [
                        {
                            "event": 1,
                            "event_id": "7047389",
                            "date": "01/09/2026",
                            "title": "DE - Ato",
                            "active": True,
                            "documents": [
                                {
                                    "key": "102390/2026|7047389|informacao-1",
                                    "id": "informacao-1",
                                    "title": "Ato",
                                    "extension": ".pdf",
                                    "sha256": "a" * 64,
                                    "path": "processos\\102390-2026\\evento-0001-7047389\\documento-001-Ato.pdf",
                                    "duplicate_of": None,
                                    "previous_versions": [],
                                    "status": "complete",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_the_promoted_index_scans_a_real_layout(self):
        index = archive_index.scan_archive(self.archive_root)

        keys = [str(item.get("key")) for item in index.get("processes", [])]
        self.assertIn("102390/2026", keys)

    def test_the_adapter_resolves_the_promoted_engine_package(self):
        module = legacy_adapter._engine()

        self.assertEqual(module.__name__, "app.analysis.engine.incremental_pipeline")
        self.assertTrue(callable(module.analyze_process))

    def test_an_unknown_process_is_reported_instead_of_analyzed(self):
        with self.assertRaises(KeyError):
            incremental_pipeline.analyze_process(
                self.archive_root,
                "999999/2026",
                tesseract=Path("tesseract-inexistente"),
                tessdata=Path("tessdata-inexistente"),
            )

    def test_an_invalid_process_key_is_refused(self):
        with self.assertRaises(ValueError):
            incremental_pipeline.analyze_process(
                self.archive_root,
                "nao-e-uma-chave",
                tesseract=Path("tesseract-inexistente"),
                tessdata=Path("tessdata-inexistente"),
            )

    def test_the_promoted_pipeline_publishes_only_results(self):
        revision = incremental_pipeline.publish_results(
            self.archive_root, {"102390/2026": {"process": "102390/2026", "status": "complete", "blocks": []}}
        )

        published = self.archive_root / "publicacoes" / str(revision)
        self.assertEqual(revision, 1)
        self.assertTrue((published / "resultados.json").is_file())
        # The legacy presentation artifacts must not be published any more.
        self.assertFalse((published / "dataset.json").is_file())
        self.assertFalse((published / "review-data.json").is_file())
        self.assertEqual(
            incremental_pipeline.current_results(self.archive_root)["102390/2026"]["status"],
            "complete",
        )

    def test_publishing_keeps_only_two_revisions(self):
        for index in range(3):
            incremental_pipeline.publish_results(
                self.archive_root,
                {f"10239{index}/2026": {"process": f"10239{index}/2026", "status": "complete", "blocks": []}},
            )

        revisions = sorted(
            path.name for path in (self.archive_root / "publicacoes").iterdir() if path.is_dir()
        )
        self.assertEqual(len(revisions), 2)


if __name__ == "__main__":
    unittest.main()
