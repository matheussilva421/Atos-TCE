"""Tests for Mesa-controlled e-Contas acquisition (M3)."""

import json
import hashlib
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.jobs import ACQUISITION_STATES, JOB_STATUSES, JobManager
from app.core.store import SCHEMA_V1, SCHEMA_V2, SCHEMA_VERSION, Store
from app.econtas.legacy_queue import (
    FrozenQueueError,
    read_frozen_queue,
    write_frozen_queue,
)
from app.econtas.collector import (
    CollectorRequest,
    build_collector_command,
    parse_summary_line,
    redact,
    run_collector,
)
from app.econtas.service import AcquisitionError, AcquisitionService

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_APP_DIR = REPO_ROOT / "work" / "tce-extractor" / "portable" / "app"


def legacy_load_frozen_queue(path, lot_number=None):
    """Load the proven validator exactly as the collector does."""

    if str(LEGACY_APP_DIR) not in sys.path:
        sys.path.insert(0, str(LEGACY_APP_DIR))
    import importlib

    module = importlib.import_module("frozen_queue")
    if lot_number is None:
        return module.load_frozen_queue(Path(path))
    return module.load_frozen_queue(Path(path), lot_number=lot_number)


def powershell_read_frozen_queue(path):
    script = (
        "Import-Module '.\\work\\tce-extractor\\portable\\TceFrozenQueue.psm1'; "
        f"Read-TceFrozenQueue -Path '{path}' | ConvertTo-Json -Depth 10 -Compress"
    )
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def seed_pending(store, keys, *, classification="PRECISA_COMPLEMENTAR"):
    """Create processes the way a real Área Restrita scan would."""

    rows = [
        {
            "process_key": key,
            "interested": "Pessoa Exemplo",
            "interested_normalized": "pessoa exemplo",
            "classification": classification,
            "needs_complement": classification == "PRECISA_COMPLEMENTAR",
        }
        for key in keys
    ]
    store.create_area_scan(
        source_scope="sector_finalistic",
        marker_label="PROFESSOR - IPERN - 2 RUBRICAS",
        marker_value="6189",
        rows=rows,
    )
    return store.list_processes()


class AcquisitionTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.manager = JobManager(self.store)


class JobStateTests(AcquisitionTestCase):
    def test_job_tracks_completed_and_failed_items(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026"])
        job_id = self.manager.create("acquisition", [row["id"] for row in rows])
        self.manager.start(job_id)
        self.manager.mark_item(job_id, rows[0]["id"], "DOWNLOADED")
        self.manager.mark_item(job_id, rows[1]["id"], "FAILED", "auth required")
        self.manager.finish(job_id)

        job = self.store.get_job(job_id)

        self.assertEqual(job["completed"], 1)
        self.assertEqual(job["failed"], 1)
        self.assertEqual(job["status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(job["total"], 2)

    def test_a_new_job_starts_pending_with_its_items(self):
        rows = seed_pending(self.store, ["102390/2026"])

        job_id = self.manager.create("acquisition", [rows[0]["id"]])

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "PENDING")
        self.assertEqual(job["total"], 1)
        self.assertEqual(job["job_type"], "acquisition")
        items = self.store.list_job_items(job_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["state"], "QUEUED")

    def test_start_records_running_and_started_at(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])

        self.manager.start(job_id)

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "RUNNING")
        self.assertTrue(job["started_at"])

    def test_finish_without_failures_is_completed(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026"])
        job_id = self.manager.create("acquisition", [row["id"] for row in rows])
        self.manager.start(job_id)
        for row in rows:
            self.manager.mark_item(job_id, row["id"], "DOWNLOADED")

        self.manager.finish(job_id)

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(job["completed"], 2)
        self.assertEqual(job["failed"], 0)
        self.assertTrue(job["finished_at"])

    def test_marking_an_item_updates_the_process_acquisition_state(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)

        self.manager.mark_item(job_id, rows[0]["id"], "DOWNLOADED")
        self.assertEqual(self.store.get_process(rows[0]["id"])["acquisition_state"], "DOWNLOADED")

        self.manager.mark_item(job_id, rows[0]["id"], "FAILED", "portal sem login")
        process = self.store.get_process(rows[0]["id"])
        self.assertEqual(process["acquisition_state"], "FAILED")

    def test_repeating_an_item_state_keeps_one_row(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)

        self.manager.mark_item(job_id, rows[0]["id"], "DOWNLOADING")
        self.manager.mark_item(job_id, rows[0]["id"], "DOWNLOADED")

        items = self.store.list_job_items(job_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["state"], "DOWNLOADED")
        self.assertEqual(items[0]["error"], None)

    def test_failed_item_keeps_its_error_message(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)

        self.manager.mark_item(job_id, rows[0]["id"], "FAILED", "tempo esgotado")

        self.assertEqual(self.store.list_job_items(job_id)[0]["error"], "tempo esgotado")

    def test_an_unknown_state_is_refused(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])

        with self.assertRaises(ValueError):
            self.manager.mark_item(job_id, rows[0]["id"], "TALVEZ")

    def test_marking_an_unknown_process_is_refused(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])

        with self.assertRaises(ValueError):
            self.manager.mark_item(job_id, 4242, "DOWNLOADED")

    def test_pausing_a_job_records_waiting_for_login(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)

        self.manager.wait_for_login(job_id, "e-Contas pediu login")

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "WAITING_FOR_LOGIN")
        self.assertEqual(job["error"], "e-Contas pediu login")
        self.assertIn("WAITING_FOR_LOGIN", JOB_STATUSES)

    def test_the_published_vocabularies_are_stable(self):
        self.assertEqual(
            ACQUISITION_STATES, ("NOT_DOWNLOADED", "QUEUED", "DOWNLOADING", "DOWNLOADED", "FAILED")
        )
        self.assertEqual(len(set(ACQUISITION_STATES)), len(ACQUISITION_STATES))


class MissingPendingSelectionTests(AcquisitionTestCase):
    def test_only_pending_processes_without_bytes_are_selected(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026", "102392/2026"])
        self.manager.mark_downloaded(rows[0]["id"])

        selected = self.store.list_missing_pending_processes()

        self.assertEqual([row["process_key"] for row in selected], ["102391/2026", "102392/2026"])

    def test_completed_and_ambiguous_processes_are_never_selected(self):
        self.store.create_area_scan(
            source_scope="sector_finalistic",
            marker_label="M",
            marker_value="1",
            rows=[
                {
                    "process_key": "102390/2026",
                    "interested": "Pessoa Exemplo",
                    "interested_normalized": "pessoa exemplo",
                    "classification": "ATO_COMPLEMENTADO",
                    "needs_complement": False,
                },
                {
                    "process_key": "102391/2026",
                    "interested": "Outra Pessoa",
                    "interested_normalized": "outra pessoa",
                    "classification": "AMBIGUO",
                    "needs_complement": False,
                },
                {
                    "process_key": "102392/2026",
                    "interested": "Terceira Pessoa",
                    "interested_normalized": "terceira pessoa",
                    "classification": "PRECISA_COMPLEMENTAR",
                    "needs_complement": True,
                },
            ],
        )

        selected = self.store.list_missing_pending_processes()

        self.assertEqual([row["process_key"] for row in selected], ["102392/2026"])

    def test_a_failed_download_is_selected_again(self):
        rows = seed_pending(self.store, ["102390/2026"])
        job_id = self.manager.create("acquisition", [rows[0]["id"]])
        self.manager.start(job_id)
        self.manager.mark_item(job_id, rows[0]["id"], "FAILED", "rede")

        self.assertEqual(len(self.store.list_missing_pending_processes()), 1)

    def test_selection_keeps_the_area_scan_order(self):
        seed_pending(self.store, ["105000/2025", "100100/2026", "103000/2024"])

        selected = self.store.list_missing_pending_processes()

        self.assertEqual(
            [row["process_key"] for row in selected],
            ["105000/2025", "100100/2026", "103000/2024"],
        )


class FrozenQueueWriterTests(AcquisitionTestCase):
    def setUp(self):
        super().setUp()
        self.queue_path = self.data / "queues" / "fila-congelada.json"

    def write(self, keys, *, lot_size=50, source_scope="sector_finalistic", marker=None):
        return write_frozen_queue(
            [{"process_key": key} for key in keys],
            source_scope,
            marker if marker is not None else {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"},
            self.queue_path,
            lot_size,
        )

    def test_the_legacy_loader_accepts_the_written_queue(self):
        info = self.write(["102390/2026", "102391/2026"], lot_size=1)

        loaded = legacy_load_frozen_queue(self.queue_path)

        self.assertEqual(
            [item["process_key"] for item in loaded["items"]], ["102390/2026", "102391/2026"]
        )
        self.assertEqual(info.lot_count, 2)
        self.assertEqual(loaded["analysis_id"], info.analysis_id)
        self.assertEqual(loaded["dataset_sha256"], info.dataset_sha256)
        self.assertEqual(loaded["source_scope"], "sector_finalistic")
        self.assertEqual(loaded["marker"], {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"})
        self.assertEqual(loaded["queue_size"], 2)

    def test_hash_and_analysis_id_come_from_the_canonical_json(self):
        info = self.write(["102390/2026"])

        document = json.loads(self.queue_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(document["canonical_json"].encode("utf-8")).hexdigest()

        self.assertEqual(digest, info.dataset_sha256)
        self.assertEqual(document["analysis_id"], f"analysis-{digest[:24]}")
        self.assertEqual(document["schema_version"], 3)
        canonical = json.loads(document["canonical_json"])
        self.assertEqual(
            sorted(canonical), ["blocked", "observed_at", "queue", "schema_version", "spec"]
        )
        self.assertEqual(canonical["spec"]["acquisition_source"], "econtas")
        self.assertEqual(canonical["blocked"], [])

    def test_ninety_two_processes_become_two_lots_of_fifty_and_forty_two(self):
        keys = [f"{100000 + index}/2026" for index in range(92)]

        info = self.write(keys, lot_size=50)

        self.assertEqual(info.queue_size, 92)
        self.assertEqual(info.lot_count, 2)
        loaded = legacy_load_frozen_queue(self.queue_path)
        self.assertEqual(len(loaded["items"]), 92)
        second = legacy_load_frozen_queue(self.queue_path, 2)
        self.assertEqual(len(second["items"]), 42)
        self.assertEqual(second["items"][0]["process_key"], "100050/2026")

    def test_duplicate_keys_are_collapsed_keeping_the_first_position(self):
        info = self.write(["102391/2026", "102390/2026", "102391/2026"])

        self.assertEqual(info.queue_size, 2)
        loaded = legacy_load_frozen_queue(self.queue_path)
        self.assertEqual(
            [item["process_key"] for item in loaded["items"]], ["102391/2026", "102390/2026"]
        )

    def test_a_non_numeric_key_is_refused(self):
        with self.assertRaises(FrozenQueueError):
            self.write(["processo-invalido"])

    def test_an_unsupported_scope_is_refused(self):
        with self.assertRaises(FrozenQueueError):
            self.write(["102390/2026"], source_scope="outro_setor")

    def test_an_empty_plan_is_refused(self):
        with self.assertRaises(FrozenQueueError):
            self.write([])

    def test_the_powershell_validator_reads_the_same_queue(self):
        self.write(["102390/2026", "102391/2026"], lot_size=1)

        result = powershell_read_frozen_queue(self.queue_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["queue_size"], 2)
        self.assertEqual(payload["source_scope"], "sector_finalistic")

    def test_reading_back_detects_tampering(self):
        info = self.write(["102390/2026"])
        self.assertEqual(read_frozen_queue(self.queue_path)["analysis_id"], info.analysis_id)

        tampered = json.loads(self.queue_path.read_text(encoding="utf-8"))
        tampered["queue"] = [{"process_key": "999999/2026"}]
        self.queue_path.write_text(json.dumps(tampered), encoding="utf-8")

        with self.assertRaises(FrozenQueueError):
            read_frozen_queue(self.queue_path)


class CollectorCommandTests(unittest.TestCase):
    def request(self, **overrides):
        values = {
            "queue_path": Path("tmp/q.json"),
            "lot_number": 1,
            "destination": Path("data/archive"),
            "source_scope": "sector_finalistic",
        }
        values.update(overrides)
        return CollectorRequest(**values)

    def test_the_command_targets_the_proven_collector(self):
        command = build_collector_command(self.request(), REPO_ROOT)
        joined = " ".join(command)

        self.assertIn("Coletar-Processos-TCE.ps1", joined)
        self.assertIn("-FilaCongelada", command)
        self.assertIn("-NumeroLote", command)
        self.assertIn("-EscopoPortal", command)
        self.assertIn("sector_finalistic", command)
        self.assertIn("-NaoInterativo", command)
        self.assertIn("powershell.exe", command[0])

    def test_the_command_never_selects_by_hand_or_claims_the_service_lock(self):
        command = build_collector_command(self.request(), REPO_ROOT)

        self.assertNotIn("-Selecao", command)
        self.assertNotIn("-ServiceChild", command)

    def test_the_command_carries_the_mesa_queue_and_lot(self):
        command = build_collector_command(
            self.request(lot_number=3, queue_path=Path("data/queues/lote.json")), REPO_ROOT
        )

        self.assertEqual(command[command.index("-NumeroLote") + 1], "3")
        self.assertTrue(command[command.index("-FilaCongelada") + 1].endswith("lote.json"))
        self.assertEqual(command[command.index("-Destino") + 1], "data\\archive".replace("\\", os.sep))
        self.assertEqual(
            command[command.index("-ModoPreparacao") + 1],
            "nenhum",
            "the Mesa analyses the process itself, so the collector must not prepare",
        )
        self.assertEqual(command[command.index("-MaxDownloads") + 1], "2")

    def test_keeping_the_browser_open_is_the_default(self):
        command = build_collector_command(self.request(), REPO_ROOT)
        self.assertIn("-ManterNavegadorAberto", command)

        closed = build_collector_command(self.request(keep_browser_open=False), REPO_ROOT)
        self.assertNotIn("-ManterNavegadorAberto", closed)


class CollectorOutputTests(unittest.TestCase):
    SUMMARY = "Concluído (progressivo). Baixados: 3; reutilizados: 1; deduplicados: 2; processos com falha: 1."

    def test_the_summary_line_is_parsed(self):
        parsed = parse_summary_line(self.SUMMARY)

        self.assertEqual(parsed["downloaded"], 3)
        self.assertEqual(parsed["reused"], 1)
        self.assertEqual(parsed["deduplicated"], 2)
        self.assertEqual(parsed["failed"], 1)
        self.assertEqual(parsed["mode"], "progressivo")

    def test_a_line_without_a_summary_is_ignored(self):
        self.assertIsNone(parse_summary_line("Baixando documento 1 de 40"))

    def test_urls_and_tokens_are_redacted(self):
        redacted = redact("Baixando https://processos.tce.rn.gov.br/api?token=abc123 e Bearer eyJhbGciOi.payload")

        self.assertNotIn("processos.tce.rn.gov.br", redacted)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("eyJhbGciOi", redacted)

    def test_credentials_are_redacted(self):
        redacted = redact("senha: super-secreta")
        self.assertNotIn("super-secreta", redacted)


class FakeProcess:
    def __init__(self, lines, returncode=0):
        self.stdout = iter(lines)
        self.returncode = returncode
        self.command = None
        self.kwargs = None

    def wait(self, timeout=None):
        return self.returncode


class CollectorRunTests(unittest.TestCase):
    def run_with(self, lines, *, returncode=0, on_line=None):
        process = FakeProcess(lines, returncode)

        def runner(command, **kwargs):
            process.command = command
            process.kwargs = kwargs
            return process

        result = run_collector(
            CollectorRequest(
                queue_path=Path("tmp/q.json"),
                lot_number=1,
                destination=Path("data/archive"),
                source_scope="sector_finalistic",
            ),
            on_line,
            REPO_ROOT,
            runner=runner,
        )
        return result, process

    def test_a_successful_run_returns_the_counts(self):
        result, process = self.run_with(
            ["Preparando lote 1", CollectorOutputTests.SUMMARY]
        )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.downloaded, 3)
        self.assertEqual(result.reused, 1)
        self.assertEqual(result.deduplicated, 2)
        self.assertEqual(result.failed, 1)
        self.assertFalse(result.auth_required)
        self.assertTrue(result.summary_found)
        self.assertIsNone(result.error)
        self.assertIn("-FilaCongelada", process.command)

    def test_a_nonzero_exit_is_reported(self):
        result, _process = self.run_with(["falhou antes do resumo"], returncode=3)

        self.assertEqual(result.exit_code, 3)
        self.assertFalse(result.summary_found)
        self.assertIsNotNone(result.error)
        self.assertIn("3", result.error)

    def test_an_auth_message_is_classified_without_echoing_it(self):
        seen = []
        result, _process = self.run_with(
            ["Sessão expirada ou não autorizada. Faça login novamente antes de retomar a coleta."],
            on_line=seen.append,
        )

        self.assertTrue(result.auth_required)
        self.assertEqual(len(seen), 1)

    def test_progress_callback_receives_only_redacted_lines(self):
        seen = []
        self.run_with(
            [
                "Abrindo https://processos.tce.rn.gov.br/#/dashboard/processos-no-setor",
                "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijklmnop",
                CollectorOutputTests.SUMMARY,
            ],
            on_line=seen.append,
        )

        self.assertEqual(len(seen), 3)
        self.assertTrue(all("processos.tce.rn.gov.br" not in line for line in seen))
        self.assertTrue(all("eyJhbGciOi" not in line for line in seen))
        self.assertTrue(any("Baixados: 3" in line for line in seen))

    def test_the_tail_keeps_recent_lines_only(self):
        result, _process = self.run_with([f"linha {index}" for index in range(80)])

        self.assertLessEqual(len(result.output_tail), 25)
        self.assertIn("linha 79", result.output_tail[-1])


PDF = b"%PDF-1.4\nbaixado pelo coletor\n%%EOF\n"


class RecordingAnalysis:
    """Stand-in for AnalysisService that only records what was scheduled."""

    def __init__(self):
        self.enqueued = []

    def enqueue(self, process_id):
        self.enqueued.append(int(process_id))
        return len(self.enqueued)
AUTH_LINE = "Sessão expirada ou não autorizada. Faça login novamente antes de retomar a coleta."


def summary(downloaded, failed=0):
    return (
        f"Concluído (progressivo). Baixados: {downloaded}; reutilizados: 0; "
        f"deduplicados: 0; processos com falha: {failed}."
    )


class AcquisitionServiceTests(AcquisitionTestCase):
    def test_a_successful_download_schedules_exactly_one_analysis_per_process(self):
        seed_pending(self.store, ["102390/2026", "102391/2026", "102392/2026"])
        runner, _calls = self.make_runner([["102390/2026", "102391/2026"], ["102392/2026"]])
        analysis = RecordingAnalysis()
        service = AcquisitionService(
            self.store,
            self.data,
            repo_root=REPO_ROOT,
            runner=runner,
            lot_size=2,
            analysis=analysis,
        )

        job_id = service.start(service.plan_pending())
        service.run(job_id)

        self.assertEqual(len(analysis.enqueued), 3)
        self.assertEqual(len(set(analysis.enqueued)), 3, "one analysis job per process")

    def write_lot_files(self, keys):
        """Simulate what the proven collector writes into the acervo."""

        for key in keys:
            folder = (
                self.data
                / "archive"
                / "processos"
                / key.replace("/", "-")
                / f"evento-0001-{key.replace('/', '')}01"
            )
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "documento-001-Ato.pdf").write_bytes(PDF)

    def make_runner(self, keys_by_lot, *, auth_on_lot=None, fail_on_lot=None):
        calls = []

        def runner(command, **kwargs):
            number = int(command[command.index("-NumeroLote") + 1])
            calls.append(number)
            if auth_on_lot == number:
                return FakeProcess([AUTH_LINE], 0)
            if fail_on_lot == number:
                return FakeProcess(["falha inesperada do coletor"], 1)
            self.write_lot_files(keys_by_lot[number - 1])
            return FakeProcess([summary(len(keys_by_lot[number - 1]))], 0)

        return runner, calls

    def service(self, runner, *, lot_size=2):
        return AcquisitionService(
            self.store, self.data, repo_root=REPO_ROOT, runner=runner, lot_size=lot_size
        )

    def test_plan_selects_only_missing_pending_processes_in_portal_order(self):
        rows = seed_pending(self.store, [f"{102390 + index}/2026" for index in range(92)])
        for row in rows[:10]:
            self.manager.mark_downloaded(row["id"])
        service = self.service(lambda *args, **kwargs: None, lot_size=50)

        plan = service.plan_pending()

        self.assertEqual(plan.total, 82)
        self.assertEqual(plan.lot_count, 2)
        self.assertEqual(plan.lot_size, 50)
        self.assertEqual(plan.process_keys[:3], ["102400/2026", "102401/2026", "102402/2026"])
        self.assertEqual(plan.process_keys[-1], "102481/2026")
        self.assertEqual(len(plan.lot_ids(1)), 50)
        self.assertEqual(len(plan.lot_ids(2)), 32)

    def test_each_lot_downloads_and_marks_its_processes(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026", "102392/2026"])
        runner, calls = self.make_runner([["102390/2026", "102391/2026"], ["102392/2026"]])
        service = self.service(runner)

        job_id = service.start(service.plan_pending())
        service.run(job_id)

        self.assertEqual(calls, [1, 2])
        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(job["completed"], 3)
        self.assertEqual(job["failed"], 0)
        for row in rows:
            process = self.store.get_process(row["id"])
            self.assertEqual(process["acquisition_state"], "DOWNLOADED")
            self.assertEqual(len(process["documents"]), 1)

    def test_new_downloads_become_canonical_blobs_with_hardlinked_views(self):
        seed_pending(self.store, ["102390/2026", "102391/2026"])
        runner, _calls = self.make_runner([["102390/2026", "102391/2026"]])
        service = self.service(runner)

        job_id = service.start(service.plan_pending())
        service.run(job_id)

        blobs = list((self.data / "archive" / "blobs").rglob("*.pdf"))
        self.assertEqual(len(blobs), 1)
        for key in ("102390-2026", "102391-2026"):
            view = next((self.data / "archive" / "processos" / key).rglob("*.pdf"))
            self.assertTrue(os.path.samefile(view, blobs[0]))

    def test_a_failed_lot_does_not_erase_previous_successes(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026", "102392/2026"])
        runner, calls = self.make_runner(
            [["102390/2026", "102391/2026"], ["102392/2026"]], fail_on_lot=2
        )
        service = self.service(runner)

        job_id = service.start(service.plan_pending())
        service.run(job_id)

        self.assertEqual(calls, [1, 2])
        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(job["completed"], 2)
        self.assertEqual(job["failed"], 1)
        self.assertEqual(self.store.get_process(rows[0]["id"])["acquisition_state"], "DOWNLOADED")
        self.assertEqual(self.store.get_process(rows[2]["id"])["acquisition_state"], "FAILED")

    def test_auth_required_pauses_the_job_and_stops_later_lots(self):
        rows = seed_pending(self.store, ["102390/2026", "102391/2026", "102392/2026"])
        runner, calls = self.make_runner([["102390/2026", "102391/2026"]], auth_on_lot=1)
        service = self.service(runner)

        job_id = service.start(service.plan_pending())
        service.run(job_id)

        self.assertEqual(calls, [1], "later lots must not run after an auth failure")
        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "WAITING_FOR_LOGIN")
        self.assertIn("login", job["error"])
        items = {
            int(item["process_id"]): item["state"] for item in self.store.list_job_items(job_id)
        }
        self.assertEqual(items[rows[0]["id"]], "FAILED")
        self.assertEqual(items[rows[2]["id"]], "QUEUED", "untouched items stay queued")

    def test_a_second_active_job_is_refused(self):
        seed_pending(self.store, ["102390/2026"])
        runner, _calls = self.make_runner([["102390/2026"]])
        service = self.service(runner)
        service.start(service.plan_pending())

        with self.assertRaises(AcquisitionError):
            service.start(service.plan_pending())

    def test_an_empty_plan_is_refused(self):
        service = self.service(lambda *args, **kwargs: None)

        with self.assertRaises(AcquisitionError):
            service.start(service.plan_pending())

    def test_the_frozen_queue_is_written_for_the_whole_plan(self):
        seed_pending(self.store, ["102390/2026", "102391/2026", "102392/2026"])
        runner, _calls = self.make_runner([["102390/2026", "102391/2026"]])
        service = self.service(runner)

        job_id = service.start(service.plan_pending())

        loaded = legacy_load_frozen_queue(service.queue_path(job_id))
        self.assertEqual(loaded["queue_size"], 3)
        self.assertEqual(
            [item["process_key"] for item in loaded["items"]],
            ["102390/2026", "102391/2026", "102392/2026"],
        )


class SchemaV3MigrationTests(unittest.TestCase):
    def build_v2_database(self, database: Path) -> None:
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for statement in SCHEMA_V1:
            connection.execute(statement)
        for statement in SCHEMA_V2:
            connection.execute(statement)
        connection.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '2')")
        connection.execute(
            "INSERT INTO processes (process_key, interested, interested_normalized, status, created_at, updated_at) "
            "VALUES ('102390/2026', 'Pessoa Exemplo', 'pessoa exemplo', 'PENDENTE', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO area_scans (source_scope, marker_label, marker_value, observed_at, origin, total) "
            "VALUES ('sector_finalistic', 'M', '6189', '2026-01-01T00:00:00Z', 'extension', 1)"
        )
        connection.commit()
        connection.close()

    def test_migration_from_v2_adds_acquisition_state_and_preserves_rows(self):
        with TemporaryDirectory() as tmp:
            database = Path(tmp) / "atos-tce.db"
            self.build_v2_database(database)

            store = Store.open(database)
            try:
                # The v2 database must migrate forward; the current version is
                # pinned once, in tests/test_fill_service.py.
                self.assertEqual(store.schema_version, SCHEMA_VERSION)
                processes = store.list_processes()
                self.assertEqual(len(processes), 1)
                self.assertEqual(processes[0]["acquisition_state"], "NOT_DOWNLOADED")
                self.assertEqual(store.get_area_scan(1)["total"], 1)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
