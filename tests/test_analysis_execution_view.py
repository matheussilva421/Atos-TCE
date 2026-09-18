"""The analysis engine must run against the canonical archive (M4 / M6).

The promoted engine reads ``archive/processos/<folder>/processo.json``. The M1
import writes only the documents, so the adapter has to materialise that
manifest from the canonical store before the engine runs; otherwise no
canonical process can ever be analysed.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.analysis import legacy_adapter
from app.analysis.engine.archive_index import scan_archive
from app.analysis.execution_view import ensure_process_manifest, process_manifest
from app.core.models import DocumentRecord, ProcessRecord
from app.core.store import Store

PROCESS_KEY = "100015/2026"
FOLDER = "100015-2026"
FIRST = DocumentRecord(
    source_id=f"{PROCESS_KEY}|7047389|informacao-3166843",
    event="1",
    title="Documento_Processo_Portal_Gestor",
    relative_path=(
        f"processos/{FOLDER}/evento-0001-7047389/documento-001-Documento_Processo_Portal_Gestor.pdf"
    ),
    sha256="a" * 64,
    page_count=3,
    classification="documento_processo_portal_gestor",
)
SECOND = DocumentRecord(
    source_id=f"{PROCESS_KEY}|7050000|informacao-3166900",
    event="2",
    title="Tramitacao_Processo_Administrativa",
    relative_path=f"processos/{FOLDER}/evento-0002-7050000/documento-001-Tramitacao.pdf",
    sha256="b" * 64,
    page_count=1,
)


class ExecutionViewTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name) / "data"
        self.archive = self.data_root / "archive"
        self.folder = self.archive / "processos" / FOLDER
        for document in (FIRST, SECOND):
            path = self.archive / document.relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"%PDF-1.4\nfixture\n")
        self.process = {
            "id": 1,
            "process_key": PROCESS_KEY,
            "interested": "PESSOA EXEMPLO",
            "interested_normalized": "pessoa exemplo",
            "status": "PENDENTE",
        }
        self.documents = [
            {
                "id": index + 1,
                "source_id": document.source_id,
                "event": document.event,
                "title": document.title,
                "relative_path": document.relative_path,
                "sha256": document.sha256,
                "page_count": document.page_count,
                "classification": document.classification,
                "storage_state": document.storage_state,
            }
            for index, document in enumerate((FIRST, SECOND))
        ]


class ManifestShapeTests(ExecutionViewTestCase):
    def test_manifest_is_built_from_canonical_rows(self):
        manifest = process_manifest(self.process, self.documents)

        self.assertEqual(manifest["key"], PROCESS_KEY)
        self.assertEqual(manifest["number"], "100015")
        self.assertEqual(manifest["year"], 2026)
        self.assertEqual([event["event"] for event in manifest["events"]], [1, 2])
        first_event = manifest["events"][0]
        self.assertEqual(first_event["event_id"], "7047389")
        self.assertEqual(first_event["title"], FIRST.title)
        document = first_event["documents"][0]
        self.assertEqual(document["title"], FIRST.title)
        self.assertEqual(document["extension"], ".pdf")
        self.assertEqual(document["sha256"], FIRST.sha256)
        self.assertEqual(document["status"], "complete")
        self.assertEqual(document["path"], FIRST.relative_path)
        self.assertEqual(document["key"], FIRST.source_id)
        self.assertEqual(document["id"], "informacao-3166843")

    def test_manifest_keeps_the_canonical_relative_path(self):
        manifest = process_manifest(self.process, self.documents)
        paths = [
            item["path"].replace("\\", "/")
            for event in manifest["events"]
            for item in event["documents"]
        ]

        self.assertEqual(paths, [FIRST.relative_path, SECOND.relative_path])

    def test_data_root_paths_are_rendered_relative_to_the_archive(self):
        # The documents table stores paths relative to the data root
        # (``archive/processos/...``); the engine resolves them against the
        # archive root, so the prefix must be dropped.
        documents = [
            {**self.documents[0], "relative_path": f"archive/{FIRST.relative_path}"},
            {**self.documents[1], "relative_path": f"archive\\{SECOND.relative_path}".replace("/", "\\")},
        ]

        manifest = process_manifest(self.process, documents)

        paths = [
            item["path"]
            for event in manifest["events"]
            for item in event["documents"]
        ]
        self.assertEqual(paths, [FIRST.relative_path, SECOND.relative_path])

    def test_the_engine_resolves_every_document_it_is_given(self):
        ensure_process_manifest(self.data_root, self.process, self.documents)

        index = scan_archive(self.archive)
        documents = [
            document
            for process in index["processes"]
            for event in process["events"]
            for document in event["documents"]
        ]

        self.assertEqual(len(documents), 2)
        for document in documents:
            with self.subTest(path=document.get("relative_path")):
                self.assertEqual(document["status"], "complete")
                self.assertIsNotNone(document.get("sha256"))


class ExecutionViewWiringTests(ExecutionViewTestCase):
    def test_ensure_writes_the_manifest_the_engine_expects(self):
        path = ensure_process_manifest(self.data_root, self.process, self.documents)

        self.assertTrue(path.is_file())
        self.assertEqual(path, self.folder / "processo.json")
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["key"], PROCESS_KEY)

    def test_scan_archive_sees_the_process_after_the_manifest_exists(self):
        before = scan_archive(self.archive)
        self.assertEqual(before["processes"], [])

        ensure_process_manifest(self.data_root, self.process, self.documents)

        after = scan_archive(self.archive)
        self.assertEqual([item["key"] for item in after["processes"]], [PROCESS_KEY])

    def test_ensure_is_idempotent(self):
        first = ensure_process_manifest(self.data_root, self.process, self.documents)
        once = first.read_bytes()

        second = ensure_process_manifest(self.data_root, self.process, self.documents)

        self.assertIsNone(second)
        self.assertEqual(first.read_bytes(), once)

    def test_the_adapter_writes_the_manifest_before_calling_the_engine(self):
        seen = {}

        class StubEngine:
            @staticmethod
            def analyze_process(archive_root, process_key, *, tesseract=None, tessdata=None):
                seen["manifest"] = (Path(archive_root) / "processos" / FOLDER / "processo.json").is_file()
                seen["key"] = process_key
                return {"process": process_key, "status": "partial", "blocks": []}

        original = legacy_adapter._engine
        legacy_adapter._engine = lambda: StubEngine
        self.addCleanup(setattr, legacy_adapter, "_engine", original)

        adapter = legacy_adapter.LegacyAnalysisAdapter(
            self.data_root,
            repo_root=self.data_root,
            tesseract=legacy_adapter.TesseractPaths(
                executable=self.data_root / "tesseract.exe",
                tessdata=self.data_root / "tessdata",
            ),
        )
        payload = adapter.analyze(PROCESS_KEY, process=self.process, documents=self.documents)

        self.assertTrue(seen["manifest"])
        self.assertEqual(seen["key"], PROCESS_KEY)
        self.assertEqual(payload["status"], "partial")


if __name__ == "__main__":
    unittest.main()
