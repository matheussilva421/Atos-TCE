"""Run the Task 7 extension smoke in a disposable browser profile."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Sequence

DEFAULT_SMOKE_TIMEOUT_SECONDS = 60.0
_REAP_RESERVE_SECONDS = 0.1


@dataclass(frozen=True)
class SupervisorResult:
    returncode: int | None
    timed_out: bool
    cleanup_completed: bool
    cleanup_timed_out: bool
    stdout: str = ""
    stderr: str = ""


def _cleanup_budget_seconds(timeout_seconds: float) -> float:
    return min(2.0, timeout_seconds / 2)


def _terminate_process_tree(
    process: subprocess.Popen[str], deadline: float | None = None
) -> tuple[str, str]:
    """Terminate only the worker process and descendants started by this CLI."""

    if process.poll() is not None:
        return _reap_process(process, deadline)
    if os.name == "nt":
        killer = subprocess.Popen(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _reap_process(killer, deadline)
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        return _reap_process(process, deadline)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return _reap_process(process, deadline)


def _reap_process(
    process: subprocess.Popen[str], deadline: float | None = None
) -> tuple[str, str]:
    """Drain and reap a process without waiting beyond the supplied deadline."""

    timeout = (
        max(0.0, deadline - time.monotonic()) if deadline is not None else 0.5
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stdout = error.output or ""
        stderr = error.stderr or ""
        try:
            process.kill()
        except ProcessLookupError:
            pass
        remaining = (
            max(0.0, deadline - time.monotonic())
            if deadline is not None
            else 0.5
        )
        try:
            drained_stdout, drained_stderr = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired as second_error:
            stdout = second_error.output or stdout
            stderr = second_error.stderr or stderr
        else:
            stdout = drained_stdout
            stderr = drained_stderr
    return stdout, stderr


def _start_process(command: Sequence[str]) -> subprocess.Popen[str]:
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(list(command), **kwargs)  # type: ignore[arg-type]


def _wait_process(
    process: subprocess.Popen[str],
    deadline: float,
    termination_deadline: float | None = None,
) -> tuple[str, str, bool]:
    wait_deadline = max(
        time.monotonic(), deadline - _REAP_RESERVE_SECONDS
    )
    remaining = max(0.0, wait_deadline - time.monotonic())
    try:
        stdout, stderr = process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired as error:
        terminated_stdout, terminated_stderr = _terminate_process_tree(
            process, termination_deadline or deadline
        )
        stdout = terminated_stdout or error.output or ""
        stderr = terminated_stderr or error.stderr or ""
        return stdout, stderr, True
    return stdout, stderr, False


def run_supervised(
    command: Sequence[str],
    *,
    timeout_seconds: float,
    scratch_dir: Path | None = None,
    cleanup_command: Sequence[str] | None = None,
) -> SupervisorResult:
    """Run a worker and cleanup child under one hard, parent-owned deadline."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    deadline = time.monotonic() + timeout_seconds
    cleanup_budget = (
        _cleanup_budget_seconds(timeout_seconds) if cleanup_command is not None else 0.0
    )
    worker_deadline = deadline - cleanup_budget
    try:
        worker = _start_process(command)
    except OSError as error:
        returncode = None
        timed_out = False
        stdout = ""
        stderr = f"worker startup failed: {error}"
    else:
        stdout, stderr, timed_out = _wait_process(
            worker, worker_deadline, termination_deadline=worker_deadline
        )
        returncode = worker.returncode

    cleanup_completed = scratch_dir is None or not scratch_dir.exists()
    cleanup_timed_out = False
    if cleanup_command is not None:
        try:
            cleanup = _start_process(cleanup_command)
        except OSError as error:
            cleanup_timed_out = False
            cleanup_completed = False
            stderr = f"{stderr}cleanup startup failed: {error}"
        else:
            _cleanup_stdout, cleanup_stderr, cleanup_timed_out = _wait_process(
                cleanup, deadline
            )
            if cleanup_stderr:
                stderr = f"{stderr}{cleanup_stderr}"
            cleanup_completed = (
                not cleanup_timed_out
                and cleanup.returncode == 0
                and (scratch_dir is None or not scratch_dir.exists())
            )
    elif timed_out and scratch_dir is not None:
        cleanup_completed = False

    return SupervisorResult(
        returncode=returncode,
        timed_out=timed_out,
        cleanup_completed=cleanup_completed,
        cleanup_timed_out=cleanup_timed_out,
        stdout=stdout,
        stderr=stderr,
    )


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension", type=Path)
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_float,
        default=DEFAULT_SMOKE_TIMEOUT_SECONDS,
        help="total smoke deadline, including browser startup and cleanup",
    )
    parser.add_argument(
        "--_worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--_scratch-dir",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--_cleanup-dir",
        type=Path,
        help=argparse.SUPPRESS,
    )
    return parser


def _cleanup_directory_worker(path: Path) -> int:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return 0
    return 0


def _require_worker_inputs(args: argparse.Namespace) -> None:
    missing = [
        name
        for name in ("extension", "fixture_root", "dataset", "screenshot")
        if getattr(args, name) is None
    ]
    if missing:
        raise ValueError("missing required arguments: " + ", ".join(missing))


def _worker_main(args: argparse.Namespace) -> int:
    _require_worker_inputs(args)
    from test_extension_browser import run_smoke

    result = run_smoke(
        extension=args.extension.resolve(),
        fixture_root=args.fixture_root.resolve(),
        dataset=args.dataset.resolve(),
        screenshot=args.screenshot.resolve(),
        timeout_seconds=args.timeout_seconds,
        scratch_dir=args._scratch_dir.resolve() if args._scratch_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args._cleanup_dir is not None:
        return _cleanup_directory_worker(args._cleanup_dir.resolve())
    if args._worker:
        return _worker_main(args)
    _require_worker_inputs(args)

    scratch_dir = Path(tempfile.mkdtemp(prefix="tce-extension-cli-"))
    worker_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--extension",
        str(args.extension.resolve()),
        "--fixture-root",
        str(args.fixture_root.resolve()),
        "--dataset",
        str(args.dataset.resolve()),
        "--screenshot",
        str(args.screenshot.resolve()),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--_worker",
        "--_scratch-dir",
        str(scratch_dir),
    ]
    cleanup_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--_cleanup-dir",
        str(scratch_dir),
    ]
    result = run_supervised(
        worker_command,
        timeout_seconds=args.timeout_seconds,
        scratch_dir=scratch_dir,
        cleanup_command=cleanup_command,
    )
    if result.timed_out:
        print(
            json.dumps(
                {
                    "error": "Task 7 smoke deadline exceeded",
                    "timeout_seconds": args.timeout_seconds,
                    "cleanup_completed": result.cleanup_completed,
                    "cleanup_timed_out": result.cleanup_timed_out,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 124
    if not result.cleanup_completed:
        print(
            json.dumps(
                {
                    "error": "Task 7 smoke cleanup did not complete before deadline",
                    "cleanup_timed_out": result.cleanup_timed_out,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 124
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
