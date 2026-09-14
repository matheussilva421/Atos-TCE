"""Bounded executor for the declarative QA function matrix.

The runner publishes only exit-code metadata, hashes and statuses. Command
stdout/stderr stays in memory and is never copied into the public report.
Portal cases are intentionally represented as human checkpoints.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping

from qa_workflow import load_function_matrix


REPORT_SCHEMA = "qa-matrix-v1"
VALID_STATUSES = {
    "PASS_REAL",
    "PASS_PACKAGE",
    "PASS_FIXTURE",
    "FAIL_REPRODUCED",
    "BLOCKED",
    "NOT_TESTED",
}


@dataclass(frozen=True)
class CommandCase:
    matrix_id: str
    command: tuple[str, ...]
    cwd: Path
    timeout_seconds: float
    pass_status: str
    evidence: str = "bounded command exit code and output hash"


@dataclass(frozen=True)
class CommandResult:
    matrix_id: str
    status: str
    returncode: int | None
    timed_out: bool
    duration_seconds: float
    output_sha256: str
    output_lines: int
    evidence: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def execute_case(case: CommandCase) -> CommandResult:
    """Run one bounded command without shell expansion or public log capture."""

    if case.pass_status not in VALID_STATUSES or case.pass_status in {"BLOCKED", "NOT_TESTED"}:
        raise ValueError("pass_status must be a positive QA status")
    if case.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    started = time.monotonic()
    timed_out = False
    returncode: int | None = None
    output = b""
    try:
        completed = subprocess.run(
            list(case.command),
            cwd=case.cwd,
            capture_output=True,
            timeout=case.timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        output = (completed.stdout or b"") + (completed.stderr or b"")
    except subprocess.TimeoutExpired as error:
        timed_out = True
        output = (error.stdout or b"") + (error.stderr or b"")
    except (FileNotFoundError, OSError) as error:
        output = str(type(error).__name__).encode("ascii", errors="replace")
    duration = round(time.monotonic() - started, 3)
    if timed_out or returncode is None:
        status = "BLOCKED"
    elif returncode == 0:
        status = case.pass_status
    else:
        status = "FAIL_REPRODUCED"
    return CommandResult(
        matrix_id=case.matrix_id,
        status=status,
        returncode=returncode,
        timed_out=timed_out,
        duration_seconds=duration,
        output_sha256=_sha256_bytes(output),
        output_lines=len(output.splitlines()),
        evidence=case.evidence,
    )


def _result_row(result: CommandResult) -> dict[str, Any]:
    return asdict(result)


def build_report(
    *,
    matrix: list[Mapping[str, Any]],
    results: Mapping[str, CommandResult],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a complete report, including unexecuted functions explicitly."""

    functions: list[dict[str, Any]] = []
    for item in matrix:
        matrix_id = str(item["id"])
        result = results.get(matrix_id)
        if result is None:
            status = "BLOCKED" if item["automation"] == "manual" else "NOT_TESTED"
            evidence = "human checkpoint required" if status == "BLOCKED" else "no execution evidence"
            execution: dict[str, Any] = {
                "matrix_id": matrix_id,
                "status": status,
                "evidence": evidence,
            }
        else:
            execution = _result_row(result)
            execution["evidence"] = result.evidence
        functions.append(
            {
                "id": matrix_id,
                "function": item["function"],
                "layer": item["layer"],
                "risk": item["risk"],
                "automation": item["automation"],
                "status": execution["status"],
                "evidence": execution["evidence"],
                "execution": execution,
            }
        )
    summary: dict[str, int] = {}
    for function in functions:
        summary[function["status"]] = summary.get(function["status"], 0) + 1
    return {
        "schema": REPORT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": dict(metadata),
        "summary": dict(sorted(summary.items())),
        "functions": functions,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    metadata = report.get("metadata", {})
    summary = report.get("summary", {})
    lines = [
        "# Relatório QA integral",
        "",
        f"- Schema: `{report.get('schema', REPORT_SCHEMA)}`",
        f"- Execução: `{metadata.get('run_id', 'não informado')}`",
        f"- Commit: `{metadata.get('commit', 'não informado')}`",
        "",
        "## Resumo",
        "",
        "| Estado | Quantidade |",
        "|---|---:|",
    ]
    for status, count in summary.items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(
        [
            "",
            "## Matriz por função",
            "",
            "| ID | Função | Camada | Risco | Automação | Estado | Evidência |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for item in report.get("functions", []):
        lines.append(
            "| {id} | {function} | {layer} | {risk} | {automation} | `{status}` | {evidence} |".format(
                **item
            )
        )
    lines.extend(
        [
            "",
            "Os artefatos brutos permanecem na área privada da execução e não são incorporados a este relatório.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(output_root: Path, report: Mapping[str, Any]) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "qa-report.json"
    markdown_path = output_root / "qa-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _git_revision(project_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(project_root.parent.parent), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        revision = completed.stdout.strip()
        return revision or "unavailable"
    except OSError:
        return "unavailable"


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda value: str(value).casefold()):
        if "dados-locais" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace(os.sep, "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def default_cases(project_root: Path, package_root: Path) -> list[CommandCase]:
    python = sys.executable
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    cases = [
        CommandCase(
            "web.collections",
            (npm, "test"),
            project_root / "portable" / "app" / "web",
            60,
            "PASS_FIXTURE",
            "source web unit suite; target package has separate static audit",
        ),
        CommandCase(
            "extension.panel-tabs",
            (npm, "test"),
            project_root / "portable" / "extensao-complementar-ato",
            120,
            "PASS_FIXTURE",
            "source extension Node suite; target package has separate static audit",
        ),
        CommandCase(
            "extension.fill",
            (python, "-m", "unittest", "test_extension_browser.ExtensionBrowserTests.test_chrome_fixture_smoke_uses_disposable_profile"),
            project_root,
            90,
            "PASS_FIXTURE",
        ),
        CommandCase(
            "offline.review-launcher",
            (python, "qa_integrated_workflow.py", "--project-root", str(project_root), "--fixture-only"),
            project_root,
            60,
            "PASS_FIXTURE",
        ),
    ]
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    menu_test = project_root / "tests" / "Test-PortableMenu.ps1"
    if menu_test.is_file() and powershell:
        cases.append(
            CommandCase(
                "offline.menu-suite",
                (powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(menu_test)),
                project_root,
                120,
                "PASS_FIXTURE",
            )
        )
    audit_script = package_root / "TESTAR-PACOTE.ps1"
    powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if audit_script.is_file() and powershell:
        cases.append(
            CommandCase(
                "offline.package-audit",
                (powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(audit_script), "-PackageRoot", str(package_root)),
                project_root,
                120,
                "PASS_PACKAGE",
            )
        )
    return cases


_RESULT_ALIASES = {
    "offline.menu-suite": [
        "offline.launcher-bat",
        "offline.launcher-cmd",
        "offline.menu-1",
        "offline.menu-2",
        "offline.menu-3",
        "offline.menu-4",
        "offline.menu-5",
        "offline.menu-6",
        "offline.menu-7",
        "offline.menu-8",
        "offline.menu-9",
        "offline.menu-10",
    ],
    "web.collections": ["web.pdf-viewer", "web.review-controls"],
    "extension.panel-tabs": [
        "extension.dataset",
        "extension.search-review",
        "extension.override",
        "extension.bridge",
        "extension.analysis",
        "extension.execution",
    ],
}


def expand_alias_results(results: Mapping[str, CommandResult]) -> dict[str, CommandResult]:
    expanded = dict(results)
    for source_id, aliases in _RESULT_ALIASES.items():
        result = results.get(source_id)
        if result is None:
            continue
        for alias in aliases:
            if alias not in expanded:
                expanded[alias] = replace(result, matrix_id=alias)
    return expanded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    project_root = args.project_root.resolve()
    package_root = args.package_root.resolve()
    matrix = load_function_matrix(project_root / "qa_function_matrix.json")
    raw_results = {case.matrix_id: execute_case(case) for case in default_cases(project_root, package_root)}
    results = expand_alias_results(raw_results)
    report = build_report(
        matrix=matrix,
        results=results,
        metadata={
            "run_id": f"qa-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "commit": _git_revision(project_root),
            "package_sha256": _tree_hash(package_root),
        },
    )
    paths = write_report(args.output_root.resolve(), report)
    print(json.dumps({"summary": report["summary"], "json": str(paths["json"]), "markdown": str(paths["markdown"])}, ensure_ascii=False))
    return 0 if not any(status.startswith("FAIL") for status in report["summary"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
