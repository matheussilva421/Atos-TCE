from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest
import zipfile
import threading
import time
from unittest.mock import patch

from package_complete_archive import build_complete_zip
from test_portable_end_to_end import _build_fixture_zip

APP_ROOT = Path(__file__).parent / "portable" / "app"
import sys
sys.path.insert(0, str(APP_ROOT))
from prepare_transfer import TransferBusyError, prepare_transfer  # noqa: E402


class PrepareTransferTests(unittest.TestCase):
    def test_transfer_requests_pause_and_waits_for_active_runtime_to_drain(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            (package / "acervo-tce" / "progresso.json").write_text(
                '{"schema_version":1,"revision":0,"processes":{}}', encoding="utf-8"
            )
            bridge = package / "dados-locais" / "bridge"
            bridge.mkdir(parents=True)
            marker = bridge / "collector.json"
            marker.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")

            def drain_after_pause_request():
                request = bridge / "transfer-request.json"
                deadline = time.monotonic() + 1
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                marker.unlink()

            worker = threading.Thread(target=drain_after_pause_request)
            worker.start()
            try:
                result = prepare_transfer(package, root / "transfer.zip", timeout_seconds=1)
            finally:
                worker.join(timeout=2)

            self.assertTrue(Path(result["path"]).exists())
            self.assertFalse((bridge / "transfer-request.json").exists())

    def test_transfer_timeout_reports_pending_work_without_creating_zip(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            (package / "acervo-tce" / "progresso.json").write_text(
                '{"schema_version":1,"revision":0,"processes":{}}', encoding="utf-8"
            )
            bridge = package / "dados-locais" / "bridge"
            bridge.mkdir(parents=True)
            (bridge / "collector.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
            destination = root / "transfer.zip"

            with self.assertRaisesRegex(TransferBusyError, "trabalho pendente|timeout"):
                prepare_transfer(package, destination, timeout_seconds=0.05)

            self.assertFalse(destination.exists())
            self.assertFalse((bridge / "transfer-request.json").exists())

    def test_transfer_excludes_pairing_but_keeps_progress_when_quiescent(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            (package / "acervo-tce" / "progresso.json").write_text(
                '{"schema_version":1,"revision":0,"processes":{}}', encoding="utf-8"
            )
            destination = root / "transfer.zip"

            result = prepare_transfer(package, destination)

            self.assertTrue(result["progress_included"])
            self.assertFalse(result["bridge_state_included"])
            with zipfile.ZipFile(result["path"]) as archive:
                names = archive.namelist()
            self.assertIn("acervo-tce/progresso.json", names)
            self.assertFalse(any(name.startswith("dados-locais/") for name in names))

    def test_transfer_refuses_active_bridge_without_creating_destination(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            (package / "acervo-tce" / "progresso.json").write_text(
                '{"schema_version":1,"revision":0,"processes":{}}', encoding="utf-8"
            )
            bridge = package / "dados-locais" / "bridge"
            bridge.mkdir(parents=True)
            (bridge / "service.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
            destination = root / "transfer.zip"

            with self.assertRaises(TransferBusyError):
                prepare_transfer(package, destination, timeout_seconds=0.01)

            self.assertFalse(destination.exists())

    def test_transfer_refuses_active_collector_without_creating_destination(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            bridge = package / "dados-locais" / "bridge"
            bridge.mkdir(parents=True)
            (bridge / "collector.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
            destination = root / "transfer.zip"

            with self.assertRaises(TransferBusyError):
                prepare_transfer(package, destination, timeout_seconds=0.01)

            self.assertFalse(destination.exists())

    def test_transfer_releases_operation_lock_when_build_fails(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            destination = root / "transfer.zip"

            def fail_build(*_args, **_kwargs):
                lock = package / "dados-locais" / "bridge" / ".operation.lock"
                self.assertTrue(lock.exists())
                raise RuntimeError("synthetic build failure")

            with patch("prepare_transfer.build_complete_zip", side_effect=fail_build):
                with self.assertRaisesRegex(RuntimeError, "synthetic build failure"):
                    prepare_transfer(package, destination)

            self.assertFalse((package / "dados-locais" / "bridge" / ".operation.lock").exists())

    def test_transfer_recovers_stale_marker_and_operation_lock(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            bridge = package / "dados-locais" / "bridge"
            bridge.mkdir(parents=True)
            (bridge / ".operation.lock").write_text(
                json.dumps({"pid": 999, "token": "stale"}), encoding="utf-8"
            )
            (bridge / "collector.json").write_text(
                json.dumps({"pid": 999}), encoding="utf-8"
            )
            destination = root / "transfer.zip"

            with patch("prepare_transfer._pid_is_alive", return_value=False):
                result = prepare_transfer(package, destination)

            self.assertTrue(destination.exists())
            self.assertEqual(result["collector_active_at_start"], False)
            self.assertFalse((bridge / ".operation.lock").exists())
            self.assertFalse((bridge / "collector.json").exists())

    def test_transfer_does_not_overwrite_existing_destination(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "transfer.zip"
            destination.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                prepare_transfer(root / "missing-package", destination)

    def test_transfer_rejects_destination_inside_package(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            destination = package / "exports" / "transfer.zip"

            with self.assertRaises(ValueError):
                prepare_transfer(package, destination)

            self.assertFalse(destination.exists())

    def test_transfer_requires_a_coherent_progress_snapshot(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            (package / "acervo-tce" / "progresso.json").write_text(
                '{"schema_version":1,"revision":"broken","processes":{}}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "progress"):
                prepare_transfer(package, root / "transfer.zip")


if __name__ == "__main__":
    unittest.main()
