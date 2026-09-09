"""Fail-closed validation for the local real-portal qualification gate."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


QUALIFICATION_SCHEMA_VERSION = 1
OUTCOME_CLASSIFIER_VERSION = "portal-outcome-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_VERSION_KEYS = frozenset(
    {
        "extension",
        "service_api",
        "automation_schema",
        "legal_context_schema",
        "rules",
        "outcome_classifier",
    }
)
_PAYLOAD_KEYS = frozenset(
    {"schema_version", "status", "versions", "fixture_hashes", "real_event_id"}
)


@dataclass(frozen=True)
class QualificationCheck:
    valid: bool
    reason: str


def expected_qualification_versions(extension_version: str) -> dict[str, Any]:
    """Return the versions bound to the currently shipped contracts."""
    return {
        "extension": extension_version,
        "service_api": 1,
        "automation_schema": 1,
        "legal_context_schema": 1,
        "rules": "legal-foundation-v1",
        "outcome_classifier": OUTCOME_CLASSIFIER_VERSION,
    }


def _valid_versions(value: object, expected: dict[str, Any]) -> bool:
    return isinstance(value, dict) and set(value) == _VERSION_KEYS and value == expected


def inspect_qualification(path: Path, expected_versions: dict[str, Any]) -> QualificationCheck:
    """Validate a qualification record without treating it as authorization."""
    path = Path(path)
    if not path.is_file():
        return QualificationCheck(False, "missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return QualificationCheck(False, "invalid")
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        return QualificationCheck(False, "invalid")
    if payload.get("schema_version") != QUALIFICATION_SCHEMA_VERSION:
        return QualificationCheck(False, "schema_mismatch")
    if payload.get("status") != "qualified":
        return QualificationCheck(False, "status_not_qualified")
    if not _valid_versions(payload.get("versions"), expected_versions):
        return QualificationCheck(False, "version_mismatch")
    hashes = payload.get("fixture_hashes")
    if (
        not isinstance(hashes, list)
        or not hashes
        or len(hashes) > 32
        or any(not isinstance(value, str) or not _SHA256_RE.fullmatch(value) for value in hashes)
        or len(set(hashes)) != len(hashes)
    ):
        return QualificationCheck(False, "fixture_hashes_invalid")
    event_id = payload.get("real_event_id")
    if not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id):
        return QualificationCheck(False, "real_event_id_invalid")
    return QualificationCheck(True, "qualified")
