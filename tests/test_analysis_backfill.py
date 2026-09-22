"""Regression tests for local analysis backfill and bundled PDF sources."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.analysis import MANDATORY_FIELDS
from app.analysis.engine.analysis_pipeline import build_target_manifest
from app.analysis.engine.tce_extractor import classify_document, extract_fields
from app.analysis.service import AnalysisService
from app.core.models import DocumentRecord, ProcessRecord
from app.core.store import Store


def _found(value: str) -> dict:
    return {"value": value, "status": "found", "confidence": "high"}


class _CompleteAdapter:
    def analyze(self, process_key, **kwargs):
        process = kwargs["process"]
        interested = process["interested"]
        return {
            "process": process_key,
            "status": "complete",
            "blocks": [
                {
                    "interested": interested,
                    "pending": [],
                    "fields": {
                        name: _found(f"{name}-{process_key}")
                        for name in MANDATORY_FIELDS
                    },
                }
            ],
        }


class AnalysisBackfillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        (self.data / "archive").mkdir(parents=True)
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)

    def add_process(self, key: str, interested: str, status: str, *, documents: bool = True) -> int:
        process_id = self.store.upsert_process(
            ProcessRecord(
                process_key=key,
                interested=interested,
                interested_normalized=interested.casefold(),
                status=status,
            )
        )
        self.store.set_process_acquisition_state(process_id, "DOWNLOADED")
        if documents:
            self.store.replace_documents(
                process_id,
                [
                    DocumentRecord(
                        source_id=f"{key}|1|documento",
                        event="2",
                        title="Resolucao.pdf",
                        relative_path=f"archive/processos/{key.replace('/', '-')}/Resolucao.pdf",
                        sha256="a" * 64,
                        page_count=1,
                    )
                ],
            )
        return process_id

    def test_backfill_queues_downloaded_documents_and_preserves_completed_status(self):
        pending_id = self.add_process("100001/2026", "Pessoa Pendente", "PENDENTE")
        completed_id = self.add_process("100002/2026", "Pessoa Concluida", "CONCLUÍDO")
        self.add_process("100003/2026", "Sem PDF", "PENDENTE", documents=False)
        self.add_process("100004/2026", "Ja Pronto", "PRONTO")

        service = AnalysisService(self.store, self.data, adapter=_CompleteAdapter())
        job_id, selected = service.enqueue_backfill()
        service.drain()

        self.assertEqual(selected, 2)
        self.assertEqual(self.store.get_job(job_id)["status"], "COMPLETED")
        self.assertEqual(self.store.get_process(pending_id)["status"], "PRONTO")
        self.assertEqual(self.store.get_process(completed_id)["status"], "CONCLUÍDO")
        self.assertEqual(len(self.store.get_process(completed_id)["fields"]), len(MANDATORY_FIELDS))


class BundledDocumentTests(unittest.TestCase):
    def test_deep_resolution_in_a_volume_is_classified(self):
        text = "capa e tramitação " * 200
        text += "\nRESOLUÇÃO ADMINISTRATIVA Nº 197, DE 14 DE FEVEREIRO DE 2020.\n"
        text += "O PRESIDENTE RESOLVE conceder aposentadoria voluntária."

        self.assertEqual(classify_document("Volume-Digitalizado-1", text), "resolucao_administrativa")

    def test_event_one_target_document_is_kept_for_extraction(self):
        classified = {
            "processes": [
                {
                    "key": "004731/2024",
                    "events": [
                        {
                            "event": 1,
                            "documents": [
                                {
                                    "classification": "resolucao_administrativa",
                                    "automatic_source": True,
                                    "title": "Volume-Digitalizado-1",
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        manifest = build_target_manifest(classified)

        self.assertEqual(len(manifest["processes"][0]["documents"]), 1)

    def test_resolution_page_wins_over_earlier_unrelated_matricula(self):
        pages = [
            "Interessada: DULCINEIDE DA COSTA LEITE\nMatrícula n 118.069-0",
            "RESOLUÇÃO ADMINISTRATIVA Nº 197, DE 14 DE FEVEREIRO DE 2020.\n"
            "Concede aposentadoria voluntária a DULCINEIDE DA COSTA LEITE, "
            "no cargo de PROFESSOR PN - IV, Classe \"I\", matrícula nº 86.186-3/1, "
            "nos termos do artigo 3º.",
        ]

        extraction = extract_fields(
            pages,
            process="004731/2024",
            event="1",
            document="Volume-Digitalizado-1",
            kind="resolucao_administrativa",
        )

        self.assertEqual(extraction.fields["matricula"].value, "86.186-3/1")


if __name__ == "__main__":
    unittest.main()
