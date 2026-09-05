"""Unit tests for the bounded Task 7 smoke CLI contract."""

from __future__ import annotations

import gc
import os
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

import qa_extension_runtime
from qa_extension_runtime import SupervisorResult, build_parser, run_supervised


class QaExtensionRuntimeTests(unittest.TestCase):
    def _run_with_synthetic_worker_startup_failure(
        self,
        command: list[str],
        *,
        timeout_seconds: float,
        scratch_dir: Path,
        cleanup_command: list[str],
    ) -> tuple[SupervisorResult, list[list[str]], list[subprocess.Popen[str]]]:
        started_commands: list[list[str]] = []
        processes: list[subprocess.Popen[str]] = []
        real_start_process = qa_extension_runtime._start_process

        def synthetic_start_process(
            requested_command: list[str] | tuple[str, ...],
        ) -> subprocess.Popen[str]:
            started_commands.append(list(requested_command))
            if len(started_commands) == 1:
                raise OSError("synthetic startup failure")
            process = real_start_process(requested_command)
            processes.append(process)
            return process

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("error", ResourceWarning)
            with patch.object(
                qa_extension_runtime, "_start_process", synthetic_start_process
            ):
                result = run_supervised(
                    command,
                    timeout_seconds=timeout_seconds,
                    scratch_dir=scratch_dir,
                    cleanup_command=cleanup_command,
                )

            for process in processes:
                self.assertIsNotNone(
                    process.poll(),
                    f"subprocess {process.pid} was not reaped",
                )
                self.assertIsNotNone(process.returncode)
            processes.clear()
            gc.collect()
            self.assertEqual(
                [warning for warning in caught if warning.category is ResourceWarning],
                [],
            )
        return result, started_commands, processes

    def _run_with_reap_assertions(self, *args, **kwargs):
        processes: list[subprocess.Popen[str]] = []
        real_popen = qa_extension_runtime.subprocess.Popen

        def tracking_popen(*popen_args, **popen_kwargs):
            process = real_popen(*popen_args, **popen_kwargs)
            processes.append(process)
            return process

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("error", ResourceWarning)
            with patch.object(
                qa_extension_runtime.subprocess, "Popen", tracking_popen
            ):
                result = run_supervised(*args, **kwargs)

            expected_processes = 3 if os.name == "nt" else 2
            self.assertEqual(len(processes), expected_processes)
            for process in processes:
                self.assertIsNotNone(
                    process.poll(),
                    f"subprocess {process.pid} was not reaped",
                )
                self.assertIsNotNone(process.returncode)
            processes.clear()
            gc.collect()
            self.assertEqual(
                [warning for warning in caught if warning.category is ResourceWarning],
                [],
            )
        return result

    def test_parser_exposes_required_inputs_and_bounded_timeout(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--extension",
                "extension",
                "--fixture-root",
                "fixtures",
                "--dataset",
                "dataset.json",
                "--screenshot",
                "screenshot.png",
            ]
        )

        self.assertEqual(args.extension.name, "extension")
        self.assertEqual(args.fixture_root.name, "fixtures")
        self.assertEqual(args.dataset.name, "dataset.json")
        self.assertEqual(args.screenshot.name, "screenshot.png")
        self.assertGreater(args.timeout_seconds, 0)

    def test_parser_rejects_non_positive_timeout(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--extension",
                    "extension",
                    "--fixture-root",
                    "fixtures",
                    "--dataset",
                    "dataset.json",
                    "--screenshot",
                    "screenshot.png",
                    "--timeout-seconds",
                    "0",
                ]
            )

    def test_supervisor_timeout_kills_only_isolated_child_tree_and_cleans_traceable_temp(self) -> None:
        with tempfile.TemporaryDirectory(prefix="task-7-fix1-timeout-") as parent:
            scratch = Path(parent) / "traceable-child-scratch"
            command = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; import sys, time; "
                    "p=Path(sys.argv[1]); p.mkdir(parents=True); "
                    "(p/'child-created.txt').write_text('child', encoding='utf-8'); "
                    "time.sleep(30)"
                ),
                str(scratch),
            ]
            cleanup_command = [
                sys.executable,
                "-c",
                "import shutil, sys; shutil.rmtree(sys.argv[1])",
                str(scratch),
            ]

            started = time.monotonic()
            result = self._run_with_reap_assertions(
                command,
                timeout_seconds=0.5,
                scratch_dir=scratch,
                cleanup_command=cleanup_command,
            )
            elapsed = time.monotonic() - started

            self.assertIsInstance(result, SupervisorResult)
            self.assertTrue(result.timed_out)
            self.assertTrue(result.cleanup_completed)
            self.assertLess(elapsed, 1.0)
            self.assertFalse(scratch.exists())

    def test_supervisor_cleans_after_worker_fails_before_runtime_try(self) -> None:
        with tempfile.TemporaryDirectory(prefix="task-7-fix1-failure-") as parent:
            scratch = Path(parent) / "traceable-child-scratch"
            command = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; import sys; "
                    "p=Path(sys.argv[1]); p.mkdir(parents=True); "
                    "(p/'startup-failed.txt').write_text('before try', encoding='utf-8'); "
                    "raise SystemExit(17)"
                ),
                str(scratch),
            ]
            cleanup_command = [
                sys.executable,
                "-c",
                "import shutil, sys; shutil.rmtree(sys.argv[1])",
                str(scratch),
            ]

            result = run_supervised(
                command,
                timeout_seconds=2.0,
                scratch_dir=scratch,
                cleanup_command=cleanup_command,
            )

            self.assertEqual(result.returncode, 17)
            self.assertFalse(result.timed_out)
            self.assertTrue(result.cleanup_completed)
            self.assertFalse(scratch.exists())

    def test_supervisor_cleans_existing_scratch_after_worker_startup_oserror(self) -> None:
        with tempfile.TemporaryDirectory(prefix="task-7-fix2-startup-") as parent:
            parent_path = Path(parent)
            scratch = parent_path / "traceable-child-scratch"
            scratch.mkdir()
            (scratch / "preexisting.txt").write_text("tracked", encoding="utf-8")
            sibling = parent_path / "must-not-be-removed.txt"
            sibling.write_text("outside scratch", encoding="utf-8")
            cleanup_command = [
                sys.executable,
                "-c",
                "import shutil, sys; shutil.rmtree(sys.argv[1])",
                str(scratch),
            ]

            result, started_commands, _processes = (
                self._run_with_synthetic_worker_startup_failure(
                    ["synthetic-worker"],
                    timeout_seconds=2.0,
                    scratch_dir=scratch,
                    cleanup_command=cleanup_command,
                )
            )

            self.assertIsNone(result.returncode)
            self.assertFalse(result.timed_out)
            self.assertTrue(result.cleanup_completed)
            self.assertFalse(result.cleanup_timed_out)
            self.assertIn("worker startup failed: synthetic startup failure", result.stderr)
            self.assertEqual(started_commands, [["synthetic-worker"], cleanup_command])
            self.assertFalse(scratch.exists())
            self.assertTrue(sibling.exists())

    def test_supervisor_reports_cleanup_timeout_after_worker_startup_oserror(self) -> None:
        with tempfile.TemporaryDirectory(prefix="task-7-fix2-cleanup-timeout-") as parent:
            parent_path = Path(parent)
            scratch = parent_path / "traceable-child-scratch"
            scratch.mkdir()
            (scratch / "keep-for-timeout.txt").write_text("tracked", encoding="utf-8")
            sibling = parent_path / "must-not-be-removed.txt"
            sibling.write_text("outside scratch", encoding="utf-8")
            cleanup_command = [
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
            ]

            started = time.monotonic()
            result, started_commands, _processes = (
                self._run_with_synthetic_worker_startup_failure(
                    ["synthetic-worker"],
                    timeout_seconds=0.5,
                    scratch_dir=scratch,
                    cleanup_command=cleanup_command,
                )
            )
            elapsed = time.monotonic() - started

            self.assertIsNone(result.returncode)
            self.assertFalse(result.timed_out)
            self.assertFalse(result.cleanup_completed)
            self.assertTrue(result.cleanup_timed_out)
            self.assertIn("worker startup failed: synthetic startup failure", result.stderr)
            self.assertEqual(started_commands, [["synthetic-worker"], cleanup_command])
            self.assertLess(elapsed, 1.0)
            self.assertTrue(scratch.exists())
            self.assertTrue(sibling.exists())

    def test_supervisor_reports_cleanup_timeout_without_silent_overrun(self) -> None:
        with tempfile.TemporaryDirectory(prefix="task-7-fix1-cleanup-") as parent:
            scratch = Path(parent) / "traceable-child-scratch"
            scratch.mkdir()
            (scratch / "keep-for-timeout.txt").write_text("tracked", encoding="utf-8")
            cleanup_command = [
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
            ]

            started = time.monotonic()
            result = self._run_with_reap_assertions(
                [sys.executable, "-c", "pass"],
                timeout_seconds=0.5,
                scratch_dir=scratch,
                cleanup_command=cleanup_command,
            )
            elapsed = time.monotonic() - started

            self.assertFalse(result.timed_out)
            self.assertFalse(result.cleanup_completed)
            self.assertTrue(result.cleanup_timed_out)
            self.assertLess(elapsed, 1.0)
            self.assertTrue(scratch.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
