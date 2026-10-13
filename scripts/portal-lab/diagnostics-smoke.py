#!/usr/bin/env python3
"""Offline smoke for the diagnostic recorder and its portable export."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from app.area_restrita.diagnostics import DiagnosticRecorder  # noqa: E402


def check(failures: list[str], label: str, condition: bool) -> None:
    if not condition:
        failures.append(label)


def _run_smoke() -> int:
    failures: list[str] = []
    base_time = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    time_index = 0

    def utcnow() -> datetime:
        nonlocal time_index
        value = base_time + timedelta(seconds=time_index)
        time_index += 1
        return value

    secret_sentinel = "smoke-secret-must-not-export-7f4c"
    with tempfile.TemporaryDirectory(prefix="atos-tce-diagnostics-smoke-") as temporary_root:
        recorder = DiagnosticRecorder(
            Path(temporary_root),
            build_id="smoke-build-20261006",
            extension_version="1.0.0-smoke",
            utcnow=utcnow,
        )

        scenarios = [
            {
                "component": "extension",
                "step": "form_detected",
                "elapsed_ms": 4800,
                "code": "FORM_DETECTED",
                "result": "ok",
            },
            {
                "component": "extension",
                "step": "form_detected",
                "code": "FORM_NOT_AVAILABLE",
                "result": "blocked",
                "error": f"Authorization: Bearer {secret_sentinel}",
            },
            {
                "component": "server",
                "step": "selection_published",
                "code": "STALE_FORM",
                "result": "refused",
            },
            {
                "component": "server",
                "step": "command_sent",
                "command_id": 101,
                "command_type": "FILL_FORM",
                "result": "ok",
            },
            {
                "component": "extension",
                "step": "field_write",
                "command_id": 101,
                "command_type": "FILL_FORM",
                "field": "cargo",
                "before": "",
                "proposed": "Analista",
                "elapsed_ms": 42,
                "result": "ok",
            },
            {
                "component": "extension",
                "step": "field_reread",
                "command_id": 101,
                "command_type": "FILL_FORM",
                "field": "cargo",
                "after": "Analista",
                "elapsed_ms": 18,
                "result": "ok",
            },
            {
                "component": "fill_service",
                "step": "result",
                "command_id": 101,
                "command_type": "FILL_FORM",
                "code": "FILL_COMPLETED",
                "result": "success",
            },
            {
                "component": "mesa",
                "step": "command_timeout",
                "command_id": 202,
                "command_type": "ANALYZE_AREA",
                "code": "COMMAND_TIMEOUT",
                "result": "timeout",
                "elapsed_ms": 900000,
            },
        ]
        accepted = [recorder.record(event) for event in scenarios]
        filename, archive_bytes = recorder.export_zip(
            capabilities={"qualification": "UNQUALIFIED", "token": secret_sentinel}
        )

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            expected_members = {
                "resumo.txt",
                "timeline.jsonl",
                "ambiente.json",
                "mesa.log",
                "extensao.log",
                "ultima-sessao.json",
            }
            members = set(archive.namelist())
            artifacts = {name: archive.read(name) for name in archive.namelist()}

        summary = artifacts["resumo.txt"].decode("utf-8")
        environment = json.loads(artifacts["ambiente.json"])
        timeline = [
            json.loads(line)
            for line in artifacts["timeline.jsonl"].decode("utf-8").splitlines()
            if line.strip()
        ]
        latest_session = json.loads(artifacts["ultima-sessao.json"])
        event_codes = {event.get("code") for event in timeline}
        field_steps = {
            event.get("step"): event
            for event in timeline
            if event.get("step") in {"field_write", "field_reread"}
        }

        check(
            failures,
            "eight synthetic events recorded",
            all(accepted) and len(timeline) == 8,
        )
        check(failures, "exact six ZIP members", members == expected_members)
        check(
            failures,
            "dated diagnostic ZIP filename",
            filename.startswith("diagnostico-atos-tce-20261006-") and filename.endswith(".zip"),
        )
        check(
            failures,
            "requested scenario codes",
            {"FORM_NOT_AVAILABLE", "STALE_FORM", "FILL_COMPLETED", "COMMAND_TIMEOUT"}
            <= event_codes,
        )
        check(
            failures,
            "slow form detection retains 4800 ms and SLOW",
            any(
                event.get("step") == "form_detected"
                and event.get("elapsed_ms") == 4800
                and event.get("severity") == "SLOW"
                for event in timeline
            ),
        )
        check(
            failures,
            "field write timing and proposed value",
            field_steps.get("field_write", {}).get("elapsed_ms") == 42
            and field_steps.get("field_write", {}).get("proposed") == "Analista",
        )
        check(
            failures,
            "field readback timing and value",
            field_steps.get("field_reread", {}).get("elapsed_ms") == 18
            and field_steps.get("field_reread", {}).get("after") == "Analista",
        )
        check(failures, "command IDs correlate fill boundaries", all(
            event.get("command_id") == 101
            for event in timeline
            if event.get("command_type") == "FILL_FORM"
        ))
        check(
            failures,
            "summary contains failures, timeout and SLOW",
            all(
                marker in summary
                for marker in (
                    "FORM_NOT_AVAILABLE",
                    "STALE_FORM",
                    "COMMAND_TIMEOUT",
                    "Etapas SLOW: 2",
                )
            ),
        )
        check(
            failures,
            "environment has build and extension version",
            environment.get("build_id") == "smoke-build-20261006"
            and environment.get("extension_version") == "1.0.0-smoke",
        )
        check(
            failures,
            "environment has safe capabilities",
            environment.get("capabilities") == {"qualification": "UNQUALIFIED"},
        )
        check(
            failures,
            "last-session projection matches active session",
            latest_session.get("session_id") == recorder.status().get("session_id")
            and len(latest_session.get("events", [])) == 8,
        )
        check(
            failures,
            "component logs contain their projections",
            b"command_timeout" in artifacts["mesa.log"]
            and b"field_write" in artifacts["extensao.log"],
        )
        check(
            failures,
            "secret sentinel absent from every exported member",
            all(secret_sentinel.encode("utf-8") not in body for body in artifacts.values()),
        )

    passed = 14 - len(failures)
    print(f"diagnostics smoke: {passed}/14 checks passed; {len(failures)} failed")
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


def main() -> int:
    try:
        return _run_smoke()
    except Exception:
        print("diagnostics smoke: 0 checks passed; 1 failed (execution error)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
