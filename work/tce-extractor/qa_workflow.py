"""Closed, sanitized contracts shared by the QA runner and its reports."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


QA_RUN_SCHEMA = "qa-run-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATUSES = {
    "PASS_REAL",
    "PASS_PACKAGE",
    "PASS_FIXTURE",
    "FAIL_REPRODUCED",
    "BLOCKED",
    "NOT_TESTED",
}
_SAFETY_MODES = {"observe_only", "reversible_fill"}
_MATRIX_LAYERS = {"offline", "web", "extension", "portal"}
_MATRIX_AUTOMATION = {"automatic", "manual", "fixture"}
_SENSITIVE_KEYS = {
    "authorization",
    "body",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "headers",
    "input_value",
    "password",
    "request_body",
    "response_body",
    "secret",
    "text",
    "token",
    "value",
}


class QaContractError(ValueError):
    """Raised when a QA artifact violates the closed report contract."""


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[redacted-url]"
    if not parsed.scheme or not parsed.netloc:
        return "[redacted-url]"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _sanitize_value(key: str, value: Any) -> Any:
    normalized = key.casefold()
    if normalized in _SENSITIVE_KEYS or normalized.endswith("_token"):
        return None
    if normalized in {"url", "href", "document_url"}:
        return _safe_url(str(value))
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for child_key, child_value in value.items():
            safe = _sanitize_value(str(child_key), child_value)
            if safe is not None:
                result[str(child_key)] = safe
        return result
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value]
    return value


def sanitize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return an event with private values removed while retaining structure."""

    if not isinstance(event, Mapping):
        raise QaContractError("event must be an object")
    result: dict[str, Any] = {}
    for key, value in event.items():
        safe = _sanitize_value(str(key), value)
        if safe is not None:
            result[str(key)] = safe
    return result


def build_run_document(
    *,
    package_root: Path,
    package_sha256: str,
    git_revision: str,
    run_id: str | None = None,
    browser: Mapping[str, Any],
    safety_mode: str,
    status: str,
    steps: list[Mapping[str, Any]],
    errors: list[Mapping[str, Any]],
    artifacts: Mapping[str, str],
    coverage: Mapping[str, Any] | list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a report document without exposing the absolute workspace path."""

    now = datetime.now(timezone.utc).isoformat()
    document = {
        "schema": QA_RUN_SCHEMA,
        "run_id": run_id or f"qa-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
        "created_at": now,
        "package": {"name": package_root.name, "sha256": package_sha256},
        "git": {"revision": git_revision},
        "browser": sanitize_event(browser),
        "safety_mode": safety_mode,
        "status": status,
        "steps": [sanitize_event(step) for step in steps],
        "errors": [sanitize_event(error) for error in errors],
        "artifacts": dict(artifacts),
        "coverage": deepcopy(coverage),
    }
    return document


def _validate_mapping_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise QaContractError(f"{label} has unknown keys: {sorted(unknown)}")


def validate_run_document(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the public run contract and return the original object."""

    if not isinstance(document, Mapping):
        raise QaContractError("run document must be an object")
    _validate_mapping_keys(
        document,
        {
            "schema",
            "run_id",
            "created_at",
            "package",
            "git",
            "browser",
            "safety_mode",
            "status",
            "steps",
            "errors",
            "artifacts",
            "coverage",
        },
        "run",
    )
    if document.get("schema") != QA_RUN_SCHEMA:
        raise QaContractError("unsupported QA run schema")
    if not isinstance(document.get("run_id"), str) or not document["run_id"]:
        raise QaContractError("run_id is required")
    package = document.get("package")
    if not isinstance(package, Mapping):
        raise QaContractError("package must be an object")
    _validate_mapping_keys(package, {"name", "sha256"}, "package")
    if not isinstance(package.get("name"), str) or not package["name"]:
        raise QaContractError("package.name is required")
    if not isinstance(package.get("sha256"), str) or not _SHA256.fullmatch(package["sha256"]):
        raise QaContractError("package.sha256 must be a lowercase SHA-256")
    git = document.get("git")
    if not isinstance(git, Mapping) or set(git) != {"revision"} or not git["revision"]:
        raise QaContractError("git.revision is required")
    if document.get("safety_mode") not in _SAFETY_MODES:
        raise QaContractError("unsupported safety mode")
    if document.get("status") not in _STATUSES:
        raise QaContractError("unsupported run status")
    if not isinstance(document.get("steps"), list) or not isinstance(document.get("errors"), list):
        raise QaContractError("steps and errors must be arrays")
    if not isinstance(document.get("artifacts"), Mapping):
        raise QaContractError("artifacts must be an object")
    coverage = document.get("coverage")
    if not isinstance(coverage, (Mapping, list)):
        raise QaContractError("coverage must be an object or array")
    for item in [*document["steps"], *document["errors"]]:
        if not isinstance(item, Mapping):
            raise QaContractError("steps and errors must contain objects")
        if any(str(key).casefold() in _SENSITIVE_KEYS for key in item):
            raise QaContractError("sanitized steps/errors cannot contain sensitive keys")
    return document


def write_run_document(path: Path, document: Mapping[str, Any]) -> None:
    """Validate and atomically write a UTF-8 JSON report."""

    validate_run_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def load_function_matrix(path: Path) -> list[dict[str, Any]]:
    """Load and validate the declarative function matrix."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QaContractError(f"cannot read function matrix: {path}") from error
    if not isinstance(payload, list) or not payload:
        raise QaContractError("function matrix must be a non-empty array")
    required = {"id", "function", "layer", "preconditions", "risk", "procedure", "expected", "evidence", "automation"}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or set(item) != required:
            raise QaContractError("matrix entries must use the closed function shape")
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in seen:
            raise QaContractError("matrix ids must be unique non-empty strings")
        if item["layer"] not in _MATRIX_LAYERS:
            raise QaContractError(f"unsupported matrix layer: {item['layer']}")
        if item["automation"] not in _MATRIX_AUTOMATION:
            raise QaContractError(f"unsupported matrix automation: {item['automation']}")
        for key in required - {"id", "layer", "automation"}:
            if not isinstance(item[key], str) or not item[key]:
                raise QaContractError(f"matrix field {key} must be a non-empty string")
        seen.add(item["id"])
        result.append(item)
    return result
