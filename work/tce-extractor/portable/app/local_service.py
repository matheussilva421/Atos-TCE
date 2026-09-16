"""Authenticated loopback HTTP bridge for the portable workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import argparse
from hmac import compare_digest
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import sys
import subprocess
import tempfile
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.parse import quote

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent.parent
for candidate in (APP_ROOT, PROJECT_ROOT):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from bridge_auth import BridgeAuth, BridgeAuthError
from automation_report import render_run_reports
from acquisition import build_collector_command, validate_acquisition_request, validate_source_scope
from analysis_preview import AnalysisPreviewStore, create_preview
from batch_scope import validate_batch_spec
from process_list import (
    ProcessListStore,
    import_process_workbook_bytes,
    write_analysis_report,
)
from automation_store import (
    ActiveRunError,
    AutomationStore,
    EventConflict,
    EventValidationError,
    InvalidTransition,
    LegacyEventReplayError,
    RevisionConflict as AutomationRevisionConflict,
    RunNotFound,
)
from html_generator import build_interface_payload, render_html
from legal_context import LEGAL_CONTEXT_VERSION, _normalise_interested
from prepare_transfer import _acquire_operation_lock, _active_runtime, _release_operation_lock, transfer_requested
from qualification import expected_qualification_versions, inspect_qualification
from workflow_state import RevisionConflict, WorkflowState


API_VERSION = 1
DEFAULT_PORT = 18743
FALLBACK_PORTS = tuple(range(18744, 18753))
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_AUTOMATION_IDENTITIES = 10_000
AUTOMATION_SCHEMA_VERSION = 1
RULES_VERSION = "legal-foundation-v2"
EXTENSION_VERSION = "1.1.0"
QUALIFICATION_RELATIVE_PATH = Path("automacao") / "qualificacao.json"
PROCESS_KEY_RE = re.compile(r"^\d+/\d{4}$")
PROCESS_KEY_QUERY_RE = re.compile(r"^(\d+)\s*/\s*(\d{4})$")
AUTOMATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
AUTOMATION_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ANALYSIS_ID_RE = re.compile(r"^analysis-[0-9a-f]{24}$")
ACQUISITION_JOB_ID_RE = re.compile(r"^acq-[0-9a-f]{24}$")
SOURCE_SCOPES = frozenset({"sector_finalistic", "my_processes"})
ACQUISITION_SOURCES = frozenset({"econtas"})
_COLLECTOR_SUMMARY_RE = re.compile(
    r"Concluído\s+\([^\r\n)]*\)\.\s+Baixados:\s*(?P<downloaded>\d+);\s*"
    r"reutilizados:\s*(?P<skipped>\d+);\s*deduplicados:\s*(?P<deduplicated>\d+);\s*"
    r"processos com falha:\s*(?P<failed>\d+)\.",
    re.IGNORECASE,
)
_COLLECTOR_ITEM_SUCCESS_RE = re.compile(
    r"^\s*baixados:\s*\d+;\s*já existentes:\s*\d+;\s*duplicados:\s*\d+\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_AUTOMATION_PAYLOAD_KEYS = frozenset(
    {
        "identity",
        "frame",
        "dataset_sha256",
        "context_hash",
        "item_id",
        "itemId",
        "fields",
        "reconciliation",
        "field_results",
        "fieldResults",
        "before",
        "after",
        "method",
        "origin",
        "rereads",
        "re_read",
        "reRead",
        "legal_decision",
        "legalDecision",
        "matchKinds",
        "decision",
        "citations",
        "timestamp",
        "error",
        "errors",
        "reason",
        "expected_fields_hash",
        "expectedFieldsHash",
    }
)

_EVENT_PAYLOAD_CONTRACTS = {
    "item_prepared": {
        "required": (("reason",),),
        "allowed": frozenset(
            {
                "reason",
                "identity",
                "frame",
                "dataset_sha256",
                "context_hash",
                "legalDecision",
                "matchKinds",
                "before",
                "after",
            }
        ),
    },
    "fields_verified": {
        "required": (("field_results", "fieldResults"), ("rereads", "re_read", "reRead")),
        "allowed": frozenset(
            {
                "field_results",
                "fieldResults",
                "rereads",
                "re_read",
                "reRead",
            }
        ),
    },
    "send_intent": {
        "required": (("expected_fields_hash", "expectedFieldsHash"), ("command_id", "commandId"), ("expires_at", "expiresAt")),
        "allowed": frozenset(
            {
                "expected_fields_hash",
                "expectedFieldsHash",
                "command_id",
                "commandId",
                "expires_at",
                "expiresAt",
                "identity",
                "fields",
                "method",
                "origin",
                "timestamp",
            }
        ),
    },
    "send_confirmed": {
        "required": (("identity",), ("origin",), ("timestamp",), ("fields",), ("citations",)),
        "allowed": frozenset({"identity", "fields", "origin", "timestamp", "citations", "reconciliation"}),
    },
    "item_pending": {
        "required": (("reason",),),
        "allowed": frozenset({"reason", "legal_decision", "legalDecision", "decision"}),
    },
    "item_failed": {
        "required": (("error", "errors"),),
        "allowed": frozenset({"error", "errors", "reason"}),
    },
    "send_unconfirmed": {
        "required": (("reason",), ("rereads", "re_read", "reRead")),
        "allowed": frozenset({"reason", "rereads", "re_read", "reRead", "origin", "timestamp"}),
    },
    "run_paused": {"required": (), "allowed": frozenset()},
    "run_resumed": {"required": (), "allowed": frozenset()},
    "run_stopped": {"required": (), "allowed": frozenset()},
    "run_completed": {"required": (), "allowed": frozenset()},
}


class _ApiProblem(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


class _BodyTooLarge(_ApiProblem):
    def __init__(self):
        super().__init__(413, "BODY_TOO_LARGE", "corpo excede o limite de 2 MiB")


class _DocumentNotFound(Exception):
    pass


_REVIEW_BOOTSTRAP_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Autorizando mesa local</title>
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'">
</head>
<body>
  <p id="status">Autorizando a mesa local…</p>
  <script src="/review-bootstrap.js" defer></script>
</body>
</html>
"""

_REVIEW_BOOTSTRAP_JS = """(() => {
  const status = document.getElementById('status');
  const code = new URLSearchParams(window.location.hash.slice(1)).get('bootstrap');
  if (!code) {
    status.textContent = 'Abra a mesa pelo iniciador do pacote portátil.';
    return;
  }
  fetch('/api/v1/review-session', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({code}),
  }).then(async (response) => {
    if (!response.ok) throw new Error('session rejected');
    const payload = await response.json();
    if (!payload.csrf_token) throw new Error('csrf token missing');
    window.sessionStorage.setItem('tce-review-csrf', payload.csrf_token);
    history.replaceState(null, '', '/review');
    window.location.replace('/review');
  }).catch(() => {
    status.textContent = 'Código expirado ou inválido. Feche esta aba e abra a mesa pelo iniciador.';
  });
})();
"""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _sidecar(root: Path, name: str) -> Path | None:
    for candidate in (root / name, root / "acervo-tce" / name):
        if candidate.is_file():
            return candidate
    return None


def _current_publication_dataset(root: Path) -> tuple[int, Path] | None:
    pointer_path = root / "publicacao-atual.json"
    if not pointer_path.is_file():
        return None
    try:
        pointer = _read_object(pointer_path)
        revision = pointer.get("revision")
        if type(revision) is not int or revision < 1:
            raise ValueError("revisão de publicação inválida")
        candidate = (root / "publicacoes" / str(revision) / "dataset.json").resolve()
        if not _inside(root, candidate) or not candidate.is_file():
            raise ValueError("dataset da publicação atual ausente")
        return revision, candidate
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"ponteiro de publicação inválido: {pointer_path}") from exc


def _current_publication_review(root: Path) -> tuple[int, Path] | None:
    pointer_path = root / "publicacao-atual.json"
    if not pointer_path.is_file():
        return None
    try:
        pointer = _read_object(pointer_path)
        revision = pointer.get("revision")
        if type(revision) is not int or revision < 1:
            raise ValueError("revisão de publicação inválida")
        candidate = (root / "publicacoes" / str(revision) / "review-data.json").resolve()
        if not _inside(root, candidate) or not candidate.is_file():
            raise ValueError("dados de revisão da publicação atual ausentes")
        return revision, candidate
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"ponteiro de publicação inválido: {pointer_path}") from exc


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"objeto JSON esperado: {path}")
    return value


def _safe_file(root: Path, relative_path: object) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None
    normalized = relative_path.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or ".." in parsed.parts:
        return None
    candidate = (root / Path(*parsed.parts)).resolve()
    if not _inside(root, candidate) or not candidate.is_file():
        return None
    current = candidate
    while current != root:
        if current.is_symlink():
            return None
        current = current.parent
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_range(value: str | None, size: int) -> tuple[int, int] | None:
    if value is None:
        return None
    if not value.startswith("bytes=") or "," in value:
        raise ValueError("Range inválido")
    spec = value[6:]
    if "-" not in spec:
        raise ValueError("Range inválido")
    start_text, end_text = spec.split("-", 1)
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                raise ValueError
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
    except ValueError as exc:
        raise ValueError("Range inválido") from exc
    if start < 0 or start >= size or end < start:
        raise ValueError("Range fora do arquivo")
    return start, min(end, size - 1)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _ApiProblem(400, "INVALID_PAYLOAD", "payload não é JSON serializável") from exc


def _require_exact_keys(value: dict, required: set[str], optional: set[str] = frozenset()) -> None:
    keys = set(value)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise _ApiProblem(400, "INVALID_PAYLOAD", "payload contém chaves inesperadas")


def _require_text(value: object, label: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise _ApiProblem(400, "INVALID_PAYLOAD", f"{label} inválido")
    return value


def _require_revision(value: object, label: str = "expected_revision") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _ApiProblem(400, "INVALID_REVISION", f"{label} inválida")
    return value


def _reject_private_payload(value: object) -> None:
    if isinstance(value, list):
        for child in value:
            _reject_private_payload(child)
        return
    if not isinstance(value, dict):
        return
    for key, child in value.items():
        if re.search(r"(?:token|cookie|password|session|authorization|workflow_root|root_path|absolute_path|file_path)$", str(key), re.IGNORECASE):
            raise _ApiProblem(400, "INVALID_PAYLOAD", "payload contém dado privado não permitido")
        _reject_private_payload(child)


def _logical_dataset_sha256(dataset: dict) -> str:
    batch = dataset.get("batch")
    if not isinstance(batch, dict):
        raise ValueError("dataset sem batch")
    logical = {
        "schema_version": dataset.get("schema_version"),
        "batch_id": batch.get("id"),
        "process_keys": batch.get("process_keys"),
        "records": dataset.get("records"),
    }
    return hashlib.sha256(_canonical_json(logical)).hexdigest()


def _load_current_dataset(root: Path) -> tuple[int, dict, str]:
    try:
        publication = _current_publication_dataset(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise _ApiProblem(500, "PUBLICATION_INVALID", "ponteiro de publicação inválido") from exc
    path = publication[1] if publication is not None else _sidecar(root, "dados-complementar-ato.json")
    if path is None:
        raise _ApiProblem(404, "DATASET_NOT_FOUND", "dataset não encontrado")
    try:
        dataset = _read_object(path)
        computed = _logical_dataset_sha256(dataset)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise _ApiProblem(500, "DATASET_INVALID", "dataset inválido") from exc
    declared = dataset.get("batch", {}).get("logical_sha256")
    if not isinstance(declared, str) or not SHA256_RE.fullmatch(declared) or not compare_digest(declared, computed):
        raise _ApiProblem(409, "DATASET_INVALID", "hash do dataset não corresponde ao conteúdo")
    revision = publication[0] if publication is not None else 0
    return revision, dataset, computed


def _dataset_record(dataset: dict, process_key: str, interested_normalized: str) -> dict | None:
    normalized = _normalise_interested(interested_normalized)
    for record in dataset.get("records", []):
        if not isinstance(record, dict):
            continue
        process = record.get("process")
        interested = record.get("interested")
        if not isinstance(process, dict) or not isinstance(interested, dict):
            continue
        if process.get("key") == process_key and _normalise_interested(interested.get("normalized")) == normalized:
            return record
    return None


def _canonical_process_key(value: object) -> str:
    if not isinstance(value, str):
        raise _ApiProblem(400, "INVALID_PROCESS_KEY", "process_key inválido")
    match = PROCESS_KEY_QUERY_RE.fullmatch(value.strip())
    if match is None:
        raise _ApiProblem(400, "INVALID_PROCESS_KEY", "process_key não é canônico")
    return f"{match.group(1)}/{match.group(2)}"


def _load_context_record(root: Path, process_key: str, interested_normalized: str, dataset_sha256: str) -> dict:
    context_path = root / "fundamentos-contexto.v1.json"
    if not context_path.is_file():
        raise _ApiProblem(404, "LEGAL_CONTEXT_NOT_FOUND", "contexto jurídico não encontrado")
    try:
        payload = _read_object(context_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise _ApiProblem(500, "LEGAL_CONTEXT_INVALID", "contexto jurídico inválido") from exc
    if payload.get("schema_version") != 1:
        raise _ApiProblem(409, "LEGAL_CONTEXT_SCHEMA_UNSUPPORTED", "schema do contexto jurídico incompatível")
    if payload.get("dataset_sha256") != dataset_sha256:
        raise _ApiProblem(409, "CONTEXT_DATASET_MISMATCH", "contexto jurídico pertence a outro dataset")
    expected = _normalise_interested(interested_normalized)
    records = payload.get("records")
    if not isinstance(records, list):
        raise _ApiProblem(500, "LEGAL_CONTEXT_INVALID", "registros de contexto inválidos")
    matches = [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("process_key") == process_key
        and record.get("interested_normalized") == expected
    ]
    if len(matches) != 1:
        raise _ApiProblem(404, "LEGAL_CONTEXT_NOT_FOUND", "contexto jurídico exato não encontrado")
    context = copy.deepcopy(matches[0])
    if "dataset_sha256" not in context:
        raise _ApiProblem(500, "LEGAL_CONTEXT_INVALID", "hash do registro de contexto ausente")
    if context["dataset_sha256"] != dataset_sha256:
        raise _ApiProblem(409, "CONTEXT_DATASET_MISMATCH", "registro de contexto pertence a outro dataset")
    try:
        encoded_size = len(_canonical_json(context))
    except _ApiProblem:
        raise _ApiProblem(500, "LEGAL_CONTEXT_INVALID", "contexto jurídico não serializável")
    if encoded_size > MAX_BODY_BYTES:
        context["resolution_status"] = "pending"
        reasons = context.get("status_reasons")
        if not isinstance(reasons, list):
            reasons = []
        context["status_reasons"] = [*reasons, {"code": "context_too_large"}]
    return context


def _validate_identity(value: object) -> dict:
    if not isinstance(value, dict):
        raise _ApiProblem(400, "INVALID_IDENTITY", "identidade inválida")
    _require_exact_keys(value, {"process_key", "interested_normalized", "portal_act_id"})
    process_key = _require_text(value.get("process_key"), "process_key")
    if not PROCESS_KEY_RE.fullmatch(process_key):
        raise _ApiProblem(400, "INVALID_PROCESS_KEY", "process_key não é canônico")
    interested = _require_text(value.get("interested_normalized"), "interested_normalized")
    if _normalise_interested(interested) != interested:
        raise _ApiProblem(400, "INVALID_IDENTITY", "interested_normalized deve estar normalizado")
    portal_act_id = value.get("portal_act_id")
    if portal_act_id is not None:
        portal_act_id = _require_text(portal_act_id, "portal_act_id")
    return {
        "process_key": process_key,
        "interested_normalized": interested,
        "portal_act_id": portal_act_id,
    }


def _validate_run_payload(payload: dict, *, pilot_enabled: bool = False) -> tuple[dict, str]:
    _require_exact_keys(
        payload,
        {"tab_id", "sector", "dataset_sha256", "rules_version", "event_id"},
        {
            "mode",
            "pilot_identity",
            "marker",
            "marker_value",
            "auto_submit",
            "source_scope",
            "acquisition_source",
            "lot_size",
            "analysis_id",
            "preview_hash",
        },
    )
    tab_id = payload.get("tab_id")
    if isinstance(tab_id, bool) or not isinstance(tab_id, int) or tab_id < 0:
        raise _ApiProblem(400, "INVALID_TAB_ID", "tab_id inválido")
    sector = _require_text(payload.get("sector"), "sector")
    dataset_sha256 = _require_text(payload.get("dataset_sha256"), "dataset_sha256")
    if not SHA256_RE.fullmatch(dataset_sha256):
        raise _ApiProblem(400, "INVALID_DATASET_HASH", "dataset_sha256 inválido")
    rules_version = _require_text(payload.get("rules_version"), "rules_version")
    if rules_version != RULES_VERSION:
        raise _ApiProblem(409, "RULES_VERSION_UNSUPPORTED", "rules_version incompatível")
    mode = payload.get("mode", "batch")
    if not isinstance(mode, str) or mode not in {"batch", "pilot"}:
        raise _ApiProblem(400, "INVALID_MODE", "modo de automação inválido")
    if mode == "pilot" and not pilot_enabled:
        raise _ApiProblem(409, "PILOT_DISABLED", "piloto não foi habilitado neste processo do serviço")
    pilot_identity = payload.get("pilot_identity")
    if mode == "pilot":
        if not isinstance(pilot_identity, dict):
            raise _ApiProblem(400, "INVALID_PILOT_IDENTITY", "piloto exige a identidade de um único ato")
        pilot_identity = _validate_identity(pilot_identity)
    elif pilot_identity is not None:
        raise _ApiProblem(400, "INVALID_MODE", "pilot_identity só é aceita no modo piloto")
    marker = payload.get("marker")
    if marker is not None:
        marker = _require_text(marker, "marker")
        if not marker.strip():
            raise _ApiProblem(400, "INVALID_PAYLOAD", "marker inválido")
    marker_value = payload.get("marker_value")
    if marker_value is not None:
        marker_value = _require_text(marker_value, "marker_value")
    source_scope = payload.get("source_scope")
    if source_scope is not None:
        if source_scope not in SOURCE_SCOPES:
            raise _ApiProblem(400, "INVALID_PAYLOAD", "source_scope inválido")
    acquisition_source = payload.get("acquisition_source")
    if acquisition_source is not None:
        if acquisition_source not in ACQUISITION_SOURCES:
            raise _ApiProblem(400, "INVALID_PAYLOAD", "acquisition_source inválido")
    lot_size = payload.get("lot_size")
    if lot_size is not None and (isinstance(lot_size, bool) or not isinstance(lot_size, int) or not 1 <= lot_size <= 1000):
        raise _ApiProblem(400, "INVALID_PAYLOAD", "lot_size inválido")
    analysis_id = payload.get("analysis_id")
    if analysis_id is not None and (not isinstance(analysis_id, str) or not ANALYSIS_ID_RE.fullmatch(analysis_id)):
        raise _ApiProblem(400, "INVALID_PAYLOAD", "analysis_id inválido")
    preview_hash = payload.get("preview_hash")
    if preview_hash is not None and (not isinstance(preview_hash, str) or not SHA256_RE.fullmatch(preview_hash)):
        raise _ApiProblem(400, "INVALID_PAYLOAD", "preview_hash inválido")
    auto_submit = payload.get("auto_submit", False)
    if not isinstance(auto_submit, bool):
        raise _ApiProblem(400, "INVALID_PAYLOAD", "auto_submit deve ser booleano")
    event_id = _require_text(payload.get("event_id"), "event_id")
    if not AUTOMATION_ID_RE.fullmatch(event_id):
        raise _ApiProblem(400, "INVALID_EVENT_ID", "event_id inválido")
    _reject_private_payload(payload)
    normalized = {
        "tab_id": tab_id,
        "sector": sector,
        "dataset_sha256": dataset_sha256,
        "rules_version": rules_version,
        "event_id": event_id,
        "mode": mode,
        "pilot_identity": pilot_identity,
        "auto_submit": auto_submit,
    }
    if marker is not None:
        normalized["marker"] = marker
    if marker_value is not None:
        normalized["marker_value"] = marker_value
    if source_scope is not None:
        normalized["source_scope"] = source_scope
    if acquisition_source is not None:
        normalized["acquisition_source"] = acquisition_source
    if lot_size is not None:
        normalized["lot_size"] = lot_size
    if analysis_id is not None:
        normalized["analysis_id"] = analysis_id
    if preview_hash is not None:
        normalized["preview_hash"] = preview_hash
    return normalized, event_id


def _validate_analysis_preview_payload(payload: dict) -> tuple[dict, list[dict], str]:
    _require_exact_keys(payload, {"spec", "rows", "observed_at"})
    spec = payload.get("spec")
    rows = payload.get("rows")
    observed_at = _require_text(payload.get("observed_at"), "observed_at", max_length=128)
    if not isinstance(spec, dict):
        raise _ApiProblem(400, "INVALID_ANALYSIS", "spec da análise deve ser objeto")
    if not isinstance(rows, list) or len(rows) > MAX_AUTOMATION_IDENTITIES:
        raise _ApiProblem(400, "INVALID_ANALYSIS", "rows da análise inválidas")
    _reject_private_payload(payload)
    try:
        normalized_spec = validate_batch_spec(spec)
    except (TypeError, ValueError) as error:
        raise _ApiProblem(400, "INVALID_ANALYSIS", str(error)) from error
    if any(not isinstance(row, dict) for row in rows):
        raise _ApiProblem(400, "INVALID_ANALYSIS", "cada row da análise deve ser objeto")
    return normalized_spec, rows, observed_at


def _project_analysis_snapshot(snapshot: dict) -> dict:
    return {
        key: copy.deepcopy(value)
        for key, value in snapshot.items()
        if key != "canonical_json"
    }


def _validate_queue_payload(payload: dict) -> tuple[list[dict], str, int]:
    _require_exact_keys(payload, {"identities", "event_id", "expected_revision"})
    identities = payload.get("identities")
    if not isinstance(identities, list):
        raise _ApiProblem(400, "INVALID_QUEUE", "identities deve ser uma lista")
    if len(identities) > MAX_AUTOMATION_IDENTITIES:
        raise _ApiProblem(413, "QUEUE_TOO_LARGE", "fila excede 10.000 identidades")
    normalized = [_validate_identity(item) for item in identities]
    event_id = _require_text(payload.get("event_id"), "event_id")
    if not AUTOMATION_ID_RE.fullmatch(event_id):
        raise _ApiProblem(400, "INVALID_EVENT_ID", "event_id inválido")
    expected_revision = _require_revision(payload.get("expected_revision"))
    _reject_private_payload(payload)
    return normalized, event_id, expected_revision


def _validate_event_payload(payload: dict, event_type: str) -> None:
    if not isinstance(payload, dict):
        raise _ApiProblem(400, "INVALID_EVENT", "payload do evento deve ser objeto")
    contract = _EVENT_PAYLOAD_CONTRACTS[event_type]
    if not set(payload).issubset(contract["allowed"]):
        raise _ApiProblem(400, "INVALID_EVENT", "payload do evento contém chaves inesperadas")
    for aliases in contract["required"]:
        if not any(key in payload for key in aliases):
            raise _ApiProblem(400, "INVALID_EVENT", "payload do evento está incompleto")
    string_keys = {
        "reason",
        "error",
        "origin",
        "timestamp",
        "expected_fields_hash",
        "expectedFieldsHash",
        "method",
    }
    record_keys = {
        "identity",
        "fields",
        "reconciliation",
        "before",
        "after",
        "field_results",
        "fieldResults",
        "legal_decision",
        "legalDecision",
        "decision",
    }
    list_keys = {"rereads", "re_read", "reRead", "citations", "errors"}
    for key, value in payload.items():
        if key in string_keys and (not isinstance(value, str) or not value):
            raise _ApiProblem(400, "INVALID_EVENT", f"{key} deve ser texto não vazio")
        if key in {"expected_fields_hash", "expectedFieldsHash"} and not SHA256_RE.fullmatch(value):
            raise _ApiProblem(400, "INVALID_EVENT", f"{key} deve ser SHA-256 hexadecimal")
        if key in record_keys and not isinstance(value, dict):
            raise _ApiProblem(400, "INVALID_EVENT", f"{key} deve ser objeto")
        if key in list_keys and not isinstance(value, list):
            raise _ApiProblem(400, "INVALID_EVENT", f"{key} deve ser lista")
    if event_type == "send_confirmed":
        if not payload["identity"]:
            raise _ApiProblem(400, "INVALID_EVENT", "identity de confirmação não pode ser vazio")
        if not payload["fields"]:
            raise _ApiProblem(400, "INVALID_EVENT", "fields de confirmação não pode ser vazio")
        if not payload["citations"]:
            raise _ApiProblem(400, "INVALID_EVENT", "citations de confirmação não pode ser vazio")
    if event_type == "send_intent":
        command_id = payload.get("command_id", payload.get("commandId"))
        expires_at = payload.get("expires_at", payload.get("expiresAt"))
        if not isinstance(command_id, str) or not AUTOMATION_ID_RE.fullmatch(command_id):
            raise _ApiProblem(400, "INVALID_EVENT", "command_id inválido")
        if isinstance(expires_at, bool) or not isinstance(expires_at, int) or expires_at <= 0:
            raise _ApiProblem(400, "INVALID_EVENT", "expires_at inválido")
    _canonical_json(payload)
    _reject_private_payload(payload)


def _validate_event_input(payload: dict) -> dict:
    _require_exact_keys(payload, {"event_id", "expected_revision", "item_id", "type", "payload"})
    event_id = _require_text(payload.get("event_id"), "event_id")
    if not AUTOMATION_ID_RE.fullmatch(event_id):
        raise _ApiProblem(400, "INVALID_EVENT_ID", "event_id inválido")
    expected_revision = _require_revision(payload.get("expected_revision"))
    item_id = payload.get("item_id")
    if item_id is not None:
        item_id = _require_text(item_id, "item_id")
    event_type = _require_text(payload.get("type"), "type")
    if event_type not in {
        "item_prepared", "fields_verified", "send_intent", "send_confirmed",
        "item_pending", "item_failed", "send_unconfirmed", "run_paused",
        "run_resumed", "run_stopped", "run_completed",
    }:
        raise _ApiProblem(400, "INVALID_EVENT_TYPE", "tipo de evento não aceito")
    if event_type.startswith("run_") and item_id is not None:
        raise _ApiProblem(400, "INVALID_EVENT", "evento de controle não aceita item_id")
    event_payload = payload.get("payload")
    _validate_event_payload(event_payload, event_type)
    result = {
        "event_id": event_id,
        "expected_revision": expected_revision,
        "item_id": item_id,
        "type": event_type,
        "payload": copy.deepcopy(event_payload),
    }
    return result


def _validate_control_payload(payload: dict) -> tuple[str, dict]:
    _require_exact_keys(payload, {"action", "event_id", "expected_revision"})
    action = payload.get("action")
    if action not in {"pause", "resume", "stop"}:
        raise _ApiProblem(400, "INVALID_ACTION", "ação de controle não aceita")
    event_id = _require_text(payload.get("event_id"), "event_id")
    if not AUTOMATION_ID_RE.fullmatch(event_id):
        raise _ApiProblem(400, "INVALID_EVENT_ID", "event_id inválido")
    expected_revision = _require_revision(payload.get("expected_revision"))
    _reject_private_payload(payload)
    return action, {
        "event_id": event_id,
        "expected_revision": expected_revision,
    }


def _validate_command_consume_payload(payload: dict) -> int:
    _require_exact_keys(payload, {"expected_revision"})
    return _require_revision(payload.get("expected_revision"))


def _validate_history_limit(value: str | None, maximum: int, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise _ApiProblem(400, "INVALID_LIMIT", "limit inválido") from exc
    if parsed < 1 or parsed > maximum:
        raise _ApiProblem(400, "INVALID_LIMIT", f"limit deve estar entre 1 e {maximum}")
    return parsed


def _validate_history_query(params: dict[str, list[str]]) -> tuple[int, str | None]:
    values = params.get("limit", [])
    limit = _validate_history_limit(values[0] if values else None, 100, 20)
    before_values = params.get("before", [])
    before = before_values[0] if before_values else None
    if before is not None and (not before or len(before) > 512):
        raise _ApiProblem(400, "INVALID_CURSOR", "cursor inválido")
    if any(key not in {"limit", "before"} for key in params):
        raise _ApiProblem(400, "INVALID_QUERY", "parâmetro de histórico não aceito")
    return limit, before


def _validate_event_history_query(params: dict[str, list[str]]) -> tuple[int, int]:
    after_values = params.get("after", [])
    limit_values = params.get("limit", [])
    try:
        after = int(after_values[0]) if after_values else 0
    except (TypeError, ValueError) as exc:
        raise _ApiProblem(400, "INVALID_AFTER", "after inválido") from exc
    if after < 0:
        raise _ApiProblem(400, "INVALID_AFTER", "after inválido")
    limit = _validate_history_limit(limit_values[0] if limit_values else None, 500, 100)
    if any(key not in {"after", "limit"} for key in params):
        raise _ApiProblem(400, "INVALID_QUERY", "parâmetro de eventos não aceito")
    return after, limit


def _automation_item_id(identity: dict) -> str:
    portal_act_id = identity.get("portal_act_id")
    if isinstance(portal_act_id, str) and portal_act_id:
        return portal_act_id
    return str(identity.get("process_key", ""))


def _acquisition_item_projection(item: object, index: int, lot_number: int) -> dict[str, int | str]:
    raw_ordinal = item.get("ordinal") if isinstance(item, dict) else None
    ordinal = raw_ordinal if isinstance(raw_ordinal, int) and raw_ordinal > 0 else index + 1
    return {"item_id": f"item-{ordinal}", "ordinal": ordinal, "lot_number": lot_number}


def _acquisition_lot_projection(lot: dict, status: str) -> dict[str, object]:
    items = [
        {"item_id": item["item_id"], "ordinal": item["ordinal"], "status": status}
        for item in lot.get("items", [])
        if isinstance(item, dict)
    ]
    return {
        "lot_number": lot["lot_number"],
        "status": status,
        "item_count": len(items),
        "items": items,
    }


def _acquisition_status_payload(job: dict[str, object], status: str) -> dict[str, object]:
    lots = [
        _acquisition_lot_projection(lot, status)
        for lot in job.get("lots", [])
        if isinstance(lot, dict)
    ]
    items = [item for lot in lots for item in lot["items"]]
    lot = lots[0] if len(lots) == 1 else {
        "lot_number": 0,
        "status": status,
        "item_count": len(items),
        "items": items,
    }
    return {"lot": lot, "lots": lots, "items": items}


def _collector_outcome(log_path: object, expected_item_count: object) -> str:
    """Require the collector's explicit per-item success protocol.

    The PowerShell collector can print its final ``Concluído`` summary after
    an auth failure and still exit with code zero.  A return code therefore
    cannot be treated as the acquisition outcome on its own.
    """

    if not isinstance(log_path, Path) or not isinstance(expected_item_count, int) or expected_item_count <= 0:
        return "missing"
    try:
        output = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "missing"
    summaries = list(_COLLECTOR_SUMMARY_RE.finditer(output))
    if not summaries:
        return "missing"
    summary = summaries[-1]
    if int(summary.group("failed")) != 0:
        return "failed"
    successful_items = len(_COLLECTOR_ITEM_SUCCESS_RE.findall(output))
    return "success" if successful_items == expected_item_count else "incomplete"


def _project_automation_snapshot(snapshot: dict, run_id: str, *, include_reports: bool = True) -> dict:
    items = [
        {
            "item_id": _automation_item_id(item["identity"]),
            "ordinal": item["ordinal"],
            "identity": {
                "process_key": item["identity"].get("process_key"),
                "interested_normalized": item["identity"].get("interested_normalized"),
                "portal_act_id": item["identity"].get("portal_act_id"),
            },
            "state": item["state"],
        }
        for item in snapshot.get("items", [])
    ]
    last_confirmed = snapshot.get("last_confirmed")
    last_confirmed_item_id = None
    if isinstance(last_confirmed, dict):
        try:
            identity = json.loads(str(last_confirmed.get("identity_key", "{}")))
            if isinstance(identity, dict):
                last_confirmed_item_id = _automation_item_id(identity)
        except (TypeError, json.JSONDecodeError):
            last_confirmed_item_id = None
    result = {
        "api_version": API_VERSION,
        "run_id": run_id,
        "revision": snapshot["revision"],
        "status": snapshot["state"],
        "items": items,
        "last_confirmed_item_id": last_confirmed_item_id,
    }
    stored_spec = snapshot.get("spec")
    if isinstance(stored_spec, dict):
        result["spec"] = {
            key: copy.deepcopy(stored_spec[key])
            for key in (
                "mode",
                "sector",
                "marker",
                "marker_value",
                "auto_submit",
                "source_scope",
                "acquisition_source",
                "lot_size",
                "analysis_id",
                "preview_hash",
            )
            if key in stored_spec
        }
    if include_reports:
        result["reports"] = {
            "html": f"/api/v1/automation/runs/{quote(run_id, safe='')}/report?format=html",
            "csv": f"/api/v1/automation/runs/{quote(run_id, safe='')}/report?format=csv",
        }
    return result


def _automation_store_error(error: Exception) -> _ApiProblem:
    if isinstance(error, RunNotFound):
        return _ApiProblem(404, "RUN_NOT_FOUND", str(error))
    if isinstance(error, ActiveRunError):
        return _ApiProblem(409, "ACTIVE_RUN", str(error))
    if isinstance(error, AutomationRevisionConflict):
        return _ApiProblem(409, "REVISION_CONFLICT", str(error))
    if isinstance(error, EventConflict):
        return _ApiProblem(409, "EVENT_CONFLICT", str(error))
    if isinstance(error, InvalidTransition):
        message = str(error)
        for code in (
            "COMMAND_ALREADY_CONSUMED",
            "COMMAND_EXPIRED",
            "COMMAND_NOT_READY",
            "COMMAND_NOT_FOUND",
            "PILOT_EXHAUSTED",
            "ACT_ALREADY_CONFIRMED",
            "ACT_REQUIRES_REVIEW",
            "RECONCILIATION_REQUIRED",
        ):
            if code in message:
                return _ApiProblem(409, code, message)
        return _ApiProblem(409, "INVALID_TRANSITION", str(error))
    if isinstance(error, LegacyEventReplayError):
        return _ApiProblem(409, "LEGACY_EVENT_REPLAY", str(error))
    if isinstance(error, EventValidationError):
        return _ApiProblem(400, "INVALID_EVENT", str(error))
    return _ApiProblem(500, "AUTOMATION_ERROR", "falha no diário de automação")


class _WorkflowHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, root: Path, *, automation_pilot: bool = False, enable_real_send: bool = False):
        self.workflow_root = root.resolve()
        self.package_root = self.workflow_root.parent
        self.automation_pilot = automation_pilot is True
        self.real_send_enabled = False
        if enable_real_send:
            qualification = inspect_qualification(
                self.workflow_root / QUALIFICATION_RELATIVE_PATH,
                expected_qualification_versions(EXTENSION_VERSION),
            )
            if not qualification.valid:
                raise ValueError(f"qualificação real inválida: {qualification.reason}")
            self.real_send_enabled = True
        workflow_state = WorkflowState(self.workflow_root)
        automation_store = AutomationStore(self.workflow_root)
        self.auth = BridgeAuth()
        self.selection: dict | None = None
        self.review_bootstrap_code: str | None = secrets.token_urlsafe(32)
        self._review_session_token: str | None = None
        self._review_session_expires_at = 0.0
        self._review_csrf_token: str | None = None
        self._review_lock = threading.RLock()
        try:
            super().__init__(address, _WorkflowHandler)
        except Exception:
            automation_store.close()
            workflow_state.close()
            raise
        self.workflow_state = workflow_state
        self.automation_store = automation_store
        self.analysis_previews = AnalysisPreviewStore(self.workflow_root)
        self.process_lists = ProcessListStore(self.workflow_root)
        self._acquisition_lock = threading.RLock()
        self._acquisition_jobs: dict[str, dict[str, object]] = {}
        self.service_revision = self.workflow_state.snapshot()["revision"]

    def start_analysis_acquisition(self, analysis_id: str, selection: dict[str, object]) -> dict[str, object]:
        if not ANALYSIS_ID_RE.fullmatch(analysis_id):
            raise _ApiProblem(404, "ANALYSIS_NOT_FOUND", "análise não encontrada")
        try:
            request = validate_acquisition_request(selection)
            snapshot = self.analysis_previews.load(analysis_id)
        except ValueError as error:
            if "lot_number" in str(error):
                raise _ApiProblem(400, "INVALID_ACQUISITION", str(error)) from error
            raise _ApiProblem(404, "ANALYSIS_NOT_FOUND", "análise não encontrada") from error
        lots = snapshot.get("lots")
        if not isinstance(lots, list):
            raise _ApiProblem(409, "LOTS_REQUIRED", "crie os lotes da análise antes da aquisição")
        lot = None if request["selection"] == "all" else next(
            (candidate for candidate in lots
             if isinstance(candidate, dict) and candidate.get("lot_number") == request["lot_number"]),
            None,
        )
        if request["selection"] == "lot" and lot is None:
            raise _ApiProblem(404, "LOT_NOT_FOUND", "lote não encontrado na análise")
        spec = snapshot.get("spec")
        try:
            source_scope = validate_source_scope(spec.get("source_scope") if isinstance(spec, dict) else None)
        except ValueError as error:
            raise _ApiProblem(409, "INVALID_ANALYSIS_SCOPE", str(error)) from error
        with self._acquisition_lock:
            for job in self._acquisition_jobs.values():
                if (
                    job["analysis_id"] == analysis_id
                    and job["selection"] == request["selection"]
                    and job["lot_number"] == request["lot_number"]
                    and job["process"].poll() is None  # type: ignore[union-attr]
                ):
                    raise _ApiProblem(409, "ACQUISITION_ACTIVE", "a aquisição deste lote já está em execução")
            job_id = f"acq-{secrets.token_hex(12)}"
            selected_lots = lots if request["selection"] == "all" else [lot]
            projected_lots = [
                {
                    "lot_number": candidate["lot_number"],
                    "items": [
                        _acquisition_item_projection(item, index, candidate["lot_number"])
                        for index, item in enumerate(candidate.get("items", []))
                        if isinstance(item, dict)
                    ],
                }
                for candidate in selected_lots
                if isinstance(candidate, dict)
            ]
            command = build_collector_command(
                package_root=self.package_root,
                workflow_root=self.workflow_root,
                analysis_path=self.workflow_root / "automacao" / "analises" / f"{analysis_id}.json",
                lot_number=request["lot_number"],
                source_scope=source_scope,
                python_path=self.package_root / "runtime" / "python" / "python.exe",
                tesseract_path=self.package_root / "runtime" / "tesseract" / "tesseract.exe",
                tessdata_path=self.package_root / "runtime" / "tesseract" / "tessdata",
            )
            log_directory = self.workflow_root / "automacao" / "coletas"
            log_directory.mkdir(parents=True, exist_ok=True)
            log_path = log_directory / f"{job_id}.log"
            with log_path.open("ab") as log_stream:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.package_root),
                    stdin=subprocess.DEVNULL,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            job = {
                "analysis_id": analysis_id,
                "selection": request["selection"],
                "lot_number": request["lot_number"],
                "process": process,
                "pid": process.pid,
                "started_at": time.time(),
                "lots": projected_lots,
                "expected_item_count": sum(len(lot["items"]) for lot in projected_lots),
                "log_path": log_path,
            }
            self._acquisition_jobs[job_id] = job
        result = {
            "api_version": API_VERSION,
            "analysis_id": analysis_id,
            "job_id": job_id,
            "selection": request["selection"],
            "lot_number": request["lot_number"] or 0,
            "status": "started",
            "pid": process.pid,
        }
        result.update(_acquisition_status_payload(job, "started"))
        return result

    def analysis_acquisition_status(self, analysis_id: str, job_id: str) -> dict[str, object]:
        if not ANALYSIS_ID_RE.fullmatch(analysis_id) or not ACQUISITION_JOB_ID_RE.fullmatch(job_id):
            raise _ApiProblem(404, "ACQUISITION_NOT_FOUND", "aquisição não encontrada")
        with self._acquisition_lock:
            job = self._acquisition_jobs.get(job_id)
            if job is None or job["analysis_id"] != analysis_id:
                raise _ApiProblem(404, "ACQUISITION_NOT_FOUND", "aquisição não encontrada")
            return_code = job["process"].poll()  # type: ignore[union-attr]
            collector_outcome = None
            if return_code is None:
                status = "running"
            else:
                collector_outcome = _collector_outcome(job.get("log_path"), job.get("expected_item_count"))
                status = "completed" if return_code == 0 and collector_outcome == "success" else "failed"
            result: dict[str, object] = {
                "api_version": API_VERSION,
                "analysis_id": analysis_id,
                "job_id": job_id,
                "selection": job["selection"],
                "lot_number": job["lot_number"] or 0,
                "status": status,
                "pid": job["pid"],
            }
            result.update(_acquisition_status_payload(job, status))
            if return_code is not None:
                result["return_code"] = return_code
                result["collector_outcome"] = collector_outcome
            return result

    def server_close(self):
        try:
            super().server_close()
        finally:
            workflow_state = getattr(self, "workflow_state", None)
            if workflow_state is not None:
                workflow_state.close()
            automation_store = getattr(self, "automation_store", None)
            if automation_store is not None:
                automation_store.close()

    def redeem_review_bootstrap(self, code: str) -> tuple[str, str]:
        with self._review_lock:
            if self.review_bootstrap_code is None or not compare_digest(self.review_bootstrap_code, code):
                raise ValueError("código de mesa inválido")
            self.review_bootstrap_code = None
            token = secrets.token_urlsafe(32)
            csrf_token = secrets.token_urlsafe(32)
            self._review_session_token = token
            self._review_csrf_token = csrf_token
            self._review_session_expires_at = time.time() + 8 * 60 * 60
            return token, csrf_token

    def validate_review_session(self, token: str) -> bool:
        with self._review_lock:
            if not token or self._review_session_token is None or time.time() >= self._review_session_expires_at:
                return False
            return compare_digest(self._review_session_token, token)

    def validate_review_csrf(self, token: str) -> bool:
        with self._review_lock:
            if not token or self._review_csrf_token is None or time.time() >= self._review_session_expires_at:
                return False
            return compare_digest(self._review_csrf_token, token)

    def current_review_csrf(self) -> str | None:
        with self._review_lock:
            if time.time() >= self._review_session_expires_at:
                return None
            return self._review_csrf_token


class _WorkflowHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format, *_args):
        # Request headers/body can contain pairing material; never log them.
        return

    @property
    def server_state(self) -> _WorkflowHTTPServer:
        return self.server  # type: ignore[return-value]

    def _send(self, status: int, payload: object = None, *, headers: dict[str, str | list[str]] | None = None, body: bytes | None = None) -> None:
        response = body if body is not None else _json_bytes(payload if payload is not None else {})
        response_headers = dict(headers or {})
        origin = self.headers.get("Origin")
        if self.server_state.auth.is_extension_origin(origin):
            response_headers.setdefault("Access-Control-Allow-Origin", origin)
            response_headers.setdefault("Vary", "Origin")
        self.send_response(status)
        self.send_header("Content-Length", str(len(response)))
        if body is None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        for name, value in response_headers.items():
            values = value if isinstance(value, list) else [value]
            for item in values:
                self.send_header(name, item)
        self.end_headers()
        self.wfile.write(response)

    def do_OPTIONS(self):
        if not self._valid_host():
            self._error(403, "FORBIDDEN_HOST", "Host não permitido")
            return
        origin = self.headers.get("Origin")
        if not self.server_state.auth.is_extension_origin(origin):
            self._error(403, "FORBIDDEN_ORIGIN", "Origin de extensão necessária")
            return
        requested_method = self.headers.get("Access-Control-Request-Method", "").upper()
        if requested_method not in {"GET", "POST", "PUT"}:
            self._error(405, "CORS_METHOD_NOT_ALLOWED", "método CORS não permitido")
            return
        requested_headers = {
            header.strip().casefold()
            for header in self.headers.get("Access-Control-Request-Headers", "").split(",")
            if header.strip()
        }
        allowed_headers = {"authorization", "content-type"}
        if not requested_headers.issubset(allowed_headers):
            self._error(400, "CORS_HEADERS_NOT_ALLOWED", "cabeçalhos CORS não permitidos")
            return
        self._send(
            204,
            body=b"",
            headers={
                "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Max-Age": "600",
            },
        )

    def _discard_unread_request_body(self) -> None:
        if getattr(self, "_request_body_consumed", False):
            return
        self._request_body_consumed = True
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return
        if length <= 0:
            return
        remaining = min(length, MAX_BODY_BYTES + 1)
        while remaining:
            chunk = self.rfile.read(min(64 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _error(self, status: int, code: str, message: str) -> None:
        # Auth failures can happen before a JSON request body is consumed. Drain
        # bounded bodies and close the connection so their bytes cannot be
        # parsed as a second HTTP request by the keep-alive server.
        self._discard_unread_request_body()
        self.close_connection = True
        self._send(
            status,
            {"error": {"code": code, "message": message}},
            headers={"Connection": "close"},
        )

    def _valid_host(self) -> bool:
        return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"

    def _valid_origin_header(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or self.server_state.auth.is_extension_origin(origin)

    def _authorized(self, *, allow_missing_origin: bool = False) -> bool:
        origin = self.headers.get("Origin")
        if not self._valid_host():
            return False
        if origin is None:
            if not allow_missing_origin:
                return False
        elif not self.server_state.auth.is_extension_origin(origin):
            return False
        value = self.headers.get("Authorization", "")
        if not value.startswith("Bearer "):
            return False
        return self.server_state.auth.validate(
            value[7:].strip(),
            origin,
            allow_missing_origin=allow_missing_origin,
        )

    def _valid_review_origin(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin == f"http://127.0.0.1:{self.server.server_port}"

    def _review_cookie(self) -> str | None:
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            morsel = cookies.get("tce_review")
            return morsel.value if morsel is not None else None
        except CookieError:
            return None

    def _review_authorized(self) -> bool:
        return self._valid_host() and self._valid_review_origin() and self.server_state.validate_review_session(self._review_cookie() or "")

    def _review_mutation_authorized(self) -> bool:
        origin = self.headers.get("Origin")
        csrf = self.headers.get("X-CSRF-Token", "")
        return (
            self._valid_host()
            and origin == f"http://127.0.0.1:{self.server.server_port}"
            and self.server_state.validate_review_session(self._review_cookie() or "")
            and self.server_state.validate_review_csrf(csrf)
        )

    def _private_authorized(self, *, allow_missing_origin: bool = False) -> bool:
        return self._authorized(allow_missing_origin=allow_missing_origin) or self._review_authorized()

    def _private_mutation_authorized(self) -> bool:
        return self._authorized() or self._review_mutation_authorized()

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length inválido") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            self._request_body_consumed = False
            raise _BodyTooLarge()
        self._request_body_consumed = True
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("objeto JSON esperado")
        return value

    def _require_auth(self, *, allow_missing_origin: bool = False) -> bool:
        if not self._authorized(allow_missing_origin=allow_missing_origin):
            self._error(403 if self.headers.get("Origin") and not self.server_state.auth.is_extension_origin(self.headers.get("Origin")) else 401, "UNAUTHORIZED", "autenticação local necessária")
            return False
        return True

    def _require_private_auth(self, *, allow_missing_origin: bool = False) -> bool:
        if self._private_authorized(allow_missing_origin=allow_missing_origin):
            return True
        self._error(403 if self.headers.get("Origin") and not self.server_state.auth.is_extension_origin(self.headers.get("Origin")) and not self._valid_review_origin() else 401, "UNAUTHORIZED", "autenticação local necessária")
        return False

    def _require_private_mutation_auth(self) -> bool:
        if self._private_mutation_authorized():
            return True
        origin = self.headers.get("Origin")
        forbidden_origin = origin is not None and not self.server_state.auth.is_extension_origin(origin) and not self._valid_review_origin()
        csrf_failure = self._review_authorized()
        self._error(403 if forbidden_origin or csrf_failure else 401, "UNAUTHORIZED", "autenticação local necessária")
        return False

    def _send_text(self, status: int, value: str, *, content_type: str, headers: dict[str, str] | None = None) -> None:
        self._send(status, body=value.encode("utf-8"), headers={"Content-Type": content_type, **(headers or {})})

    def _automation_snapshot(self, run_id: str, *, include_reports: bool = True) -> dict:
        try:
            snapshot = self.server_state.automation_store.snapshot(run_id)
        except Exception as error:
            raise _automation_store_error(error) from error
        return _project_automation_snapshot(snapshot, run_id, include_reports=include_reports)

    def _assert_run_dataset(self, run_snapshot: dict) -> tuple[dict, str]:
        try:
            _revision, dataset, computed = _load_current_dataset(self.server_state.workflow_root)
        except _ApiProblem:
            raise
        spec = run_snapshot.get("spec")
        if not isinstance(spec, dict) or spec.get("dataset_sha256") != computed:
            raise _ApiProblem(409, "DATASET_MISMATCH", "dataset atual difere do dataset da execução")
        return dataset, computed

    def _send_automation_capabilities(self) -> None:
        self._send(
            200,
            {
                "api_version": API_VERSION,
                "automation_schema": AUTOMATION_SCHEMA_VERSION,
                "legal_context_schema": 1,
                "rules_version": RULES_VERSION,
                "real_send_enabled": self.server_state.real_send_enabled,
                "pilot_enabled": self.server_state.automation_pilot,
                "pilot_consumes_remaining": self.server_state.automation_pilot
                and not self.server_state.automation_store.pilot_command_consumed(),
            },
        )

    def _send_legal_context(self, params: dict[str, list[str]]) -> None:
        if set(params) != {"process_key", "interested_normalized"}:
            self._error(400, "INVALID_QUERY", "process_key e interested_normalized são obrigatórios")
            return
        process_values = params.get("process_key", [])
        interested_values = params.get("interested_normalized", [])
        if len(process_values) != 1 or len(interested_values) != 1:
            self._error(400, "INVALID_QUERY", "parâmetros de contexto ambíguos")
            return
        try:
            process_key = _canonical_process_key(process_values[0])
            interested = _normalise_interested(interested_values[0])
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        if not interested:
            self._error(400, "INVALID_IDENTITY", "interested_normalized inválido")
            return
        try:
            revision, dataset, dataset_sha256 = _load_current_dataset(self.server_state.workflow_root)
            if _dataset_record(dataset, process_key, interested) is None:
                raise _ApiProblem(404, "IDENTITY_NOT_IN_DATASET", "identidade não pertence ao dataset atual")
            context = _load_context_record(
                self.server_state.workflow_root,
                process_key,
                interested,
                dataset_sha256,
            )
            context["context_revision"] = revision
            context["rules_version"] = RULES_VERSION
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        self._send(200, {"api_version": API_VERSION, "context": context})

    def _send_automation_run(self, run_id: str) -> None:
        try:
            payload = self._automation_snapshot(run_id)
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        self._send(200, payload)

    def _send_automation_runs(self, params: dict[str, list[str]]) -> None:
        try:
            limit, before = _validate_history_query(params)
            result = self.server_state.automation_store.list_runs(limit=limit, before=before)
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except Exception as error:
            problem = _automation_store_error(error)
            self._error(problem.status, problem.code, str(problem))
            return
        self._send(200, {"api_version": API_VERSION, **result})

    def _send_analysis(self, analysis_id: str) -> None:
        if not ANALYSIS_ID_RE.fullmatch(analysis_id):
            self._error(404, "ANALYSIS_NOT_FOUND", "análise não encontrada")
            return
        try:
            snapshot = self.server_state.analysis_previews.load(analysis_id)
        except ValueError:
            self._error(404, "ANALYSIS_NOT_FOUND", "análise não encontrada")
            return
        self._send(200, _project_analysis_snapshot(snapshot))

    def _create_analysis_preview(self) -> None:
        try:
            payload = self._read_json()
            spec, rows, observed_at = _validate_analysis_preview_payload(payload)
            snapshot = create_preview(
                self.server_state.workflow_root,
                spec,
                rows,
                observed_at,
            )
            saved = self.server_state.analysis_previews.save(snapshot)
        except _BodyTooLarge as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            self._error(400, "INVALID_ANALYSIS", str(error))
            return
        self._send(200, _project_analysis_snapshot(saved))

    def _import_process_list(self) -> None:
        try:
            payload = self._read_json()
            _require_exact_keys(payload, {"filename", "content_base64"})
            manifest = import_process_workbook_bytes(
                self.server_state.workflow_root,
                payload["filename"],
                payload["content_base64"],
            )
        except _BodyTooLarge as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            self._error(400, "INVALID_PROCESS_LIST", str(error))
            return
        self._send(200, manifest)

    def _create_process_list_report(self, input_list_id: str) -> None:
        try:
            manifest = self.server_state.process_lists.load(input_list_id)
            payload = self._read_json()
            _require_exact_keys(payload, {"classifications"})
            classifications = payload["classifications"]
            if not isinstance(classifications, dict):
                raise ValueError("classifications deve ser um objeto")
            for key, value in classifications.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    raise ValueError("classificação inválida")
            report_path = self.server_state.workflow_root / "automacao" / "relatorios" / f"area-restrita-{input_list_id}.xlsx"
            summary = write_analysis_report(report_path, manifest, classifications)
        except _BodyTooLarge as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            self._error(400, "INVALID_PROCESS_LIST_REPORT", str(error))
            return
        self._send(
            200,
            {
                "input_list_id": input_list_id,
                "relative_path": report_path.relative_to(self.server_state.workflow_root).as_posix(),
                "summary": summary,
            },
        )

    def _create_analysis_lots(self, analysis_id: str) -> None:
        if not ANALYSIS_ID_RE.fullmatch(analysis_id):
            self._error(404, "ANALYSIS_NOT_FOUND", "análise não encontrada")
            return
        try:
            payload = self._read_json()
            if payload:
                raise _ApiProblem(400, "INVALID_ANALYSIS", "criação de lotes não aceita campos")
            snapshot = self.server_state.analysis_previews.create_lots(analysis_id)
        except _BodyTooLarge as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except ValueError:
            self._error(404, "ANALYSIS_NOT_FOUND", "análise não encontrada")
            return
        self._send(200, _project_analysis_snapshot(snapshot))

    def _start_analysis_acquisition(self, analysis_id: str) -> None:
        if not ANALYSIS_ID_RE.fullmatch(analysis_id):
            self._error(404, "ANALYSIS_NOT_FOUND", "análise não encontrada")
            return
        try:
            payload = self._read_json()
            request = validate_acquisition_request(payload)
            result = self.server_state.start_analysis_acquisition(analysis_id, request)
        except _BodyTooLarge as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            self._error(400, "INVALID_ACQUISITION", str(error))
            return
        except OSError as error:
            self._error(503, "ACQUISITION_UNAVAILABLE", f"coleta não pôde ser iniciada: {error}")
            return
        self._send(202, result)

    def _send_analysis_acquisition_status(self, analysis_id: str, job_id: str) -> None:
        try:
            result = self.server_state.analysis_acquisition_status(analysis_id, job_id)
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        self._send(200, result)

    def _send_automation_events(self, run_id: str, params: dict[str, list[str]]) -> None:
        try:
            after, limit = _validate_event_history_query(params)
            all_events = self.server_state.automation_store.get_events(run_id, after=after)
        except _ApiProblem as problem:
            self._error(problem.status, problem.code, str(problem))
            return
        except Exception as error:
            problem = _automation_store_error(error)
            self._error(problem.status, problem.code, str(problem))
            return
        events = all_events[:limit]
        has_more = len(all_events) > limit
        next_after = events[-1]["seq"] if events and has_more else None
        self._send(200, {
            "api_version": API_VERSION,
            "events": events,
            "next_after": next_after,
            "has_more": has_more,
        })

    def _send_automation_report(self, run_id: str, params: dict[str, list[str]]) -> None:
        if set(params) != {"format"} or len(params.get("format", [])) != 1:
            self._error(400, "INVALID_QUERY", "format=html ou format=csv é obrigatório")
            return
        report_format = params["format"][0]
        if report_format not in {"html", "csv"}:
            self._error(400, "REPORT_FORMAT_UNSUPPORTED", "apenas html e csv são aceitos")
            return
        try:
            rendered = render_run_reports(
                self.server_state.automation_store,
                run_id,
                self.server_state.workflow_root,
            )
            report_path = Path(rendered[f"{report_format}_path"]).resolve()
            if not _inside(self.server_state.workflow_root, report_path) or not report_path.is_file():
                raise OSError("relatório fora da raiz do serviço")
            body = report_path.read_bytes()
        except RunNotFound as error:
            self._error(404, "RUN_NOT_FOUND", str(error))
            return
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._error(500, "REPORT_UNAVAILABLE", "relatório indisponível")
            return
        content_type = "text/html; charset=utf-8" if report_format == "html" else "text/csv; charset=utf-8"
        self._send(
            200,
            body=body,
            headers={
                "Content-Type": content_type,
                "Cache-Control": "no-store",
                "Content-Disposition": f"inline; filename=relatorio.{report_format}",
            },
        )

    def _review_payload_for_browser(self, payload: dict) -> dict:
        result = copy.deepcopy(payload)
        for process in result.get("processes", []):
            if not isinstance(process, dict):
                continue
            for collection_name in ("documents", "all_documents"):
                for document in process.get(collection_name, []):
                    if not isinstance(document, dict):
                        continue
                    document_id = document.get("document_id")
                    if isinstance(document_id, str) and document_id:
                        document["pdf_url"] = f"/api/v1/pdf/{quote(document_id, safe='')}"
        return result

    def _send_review_bootstrap(self):
        if not self._valid_host():
            self._error(403, "FORBIDDEN_HOST", "Host não permitido")
            return
        self._send_text(200, _REVIEW_BOOTSTRAP_HTML, content_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    def _send_review_html(self):
        try:
            publication = _current_publication_review(self.server_state.workflow_root)
        except (OSError, ValueError, json.JSONDecodeError):
            self._error(500, "PUBLICATION_INVALID", "ponteiro de publicação inválido")
            return
        try:
            if publication is None:
                root = self.server_state.workflow_root
                manifest = _safe_file(root, "pdfs-alvo-manifest.json")
                checkpoint = _safe_file(root, "checkpoint-extracao.json")
                if manifest is None or checkpoint is None:
                    self._error(404, "REVIEW_DATA_NOT_FOUND", "execute a extração local antes de abrir a conferência")
                    return
                payload = build_interface_payload(
                    manifest, checkpoint,
                    archive_index_path=_safe_file(root, "indice-classificado.json"),
                    visual_evidence_path=_safe_file(root, "evidencias-visuais.json"),
                    collections_path=_safe_file(root, "colecoes-processos.json"),
                )
                payload["manual_review"] = True
            else:
                payload = _read_object(publication[1])
            payload = self._review_payload_for_browser(payload)
            html = render_html(payload)
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            self._error(500, "REVIEW_DATA_INVALID", "snapshot de revisão inválido")
            return
        nonce = secrets.token_urlsafe(18)
        csrf_token = self.server_state.current_review_csrf()
        if csrf_token is None:
            self._error(401, "UNAUTHORIZED", "sessão local expirada")
            return
        html = html.replace(
            '<body data-review-mode=',
            f'<body data-review-csrf="{csrf_token}" data-review-mode=',
            1,
        )
        html = html.replace(
            "</head>",
            '<link rel="stylesheet" href="/app/web/review.css">\n'
            '<script type="module" src="/app/web/review-app.js"></script>\n'
            "</head>",
            1,
        )
        html = html.replace("<style>", f'<style nonce="{nonce}">', 1)
        html = html.replace("<script>\n(() => {", f'<script nonce="{nonce}">\n(() => {{', 1)
        self._send_text(
            200,
            html,
            content_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'nonce-{nonce}'; connect-src 'self'; frame-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'",
            },
        )

    def _send_review_asset(self, relative_path: str):
        normalized = relative_path.replace("\\", "/")
        parsed = PurePosixPath(normalized)
        asset_root = (self.server_state.workflow_root.parent / "app" / "web").resolve()
        candidate = (asset_root / Path(*parsed.parts)).resolve()
        if parsed.is_absolute() or ".." in parsed.parts or not _inside(asset_root, candidate) or not candidate.is_file():
            self._error(404, "NOT_FOUND", "asset não encontrado")
            return
        current = candidate
        while current != asset_root:
            if current.is_symlink():
                self._error(404, "NOT_FOUND", "asset não encontrado")
                return
            current = current.parent
        content_types = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".mjs": "text/javascript; charset=utf-8"}
        try:
            body = candidate.read_bytes()
        except OSError:
            self._error(404, "NOT_FOUND", "asset não encontrado")
            return
        self._send(200, body=body, headers={"Content-Type": content_types.get(candidate.suffix.lower(), "application/octet-stream"), "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/v1/health":
            if not self._valid_host() or not self._valid_origin_header():
                self._error(403, "FORBIDDEN_ORIGIN", "Host ou Origin não permitido")
                return
            self._send(
                200,
                {
                    "api_version": API_VERSION,
                    "service": "tce-portable",
                    "automation_schema": AUTOMATION_SCHEMA_VERSION,
                    "legal_context_schema": 1,
                    "rules_version": RULES_VERSION,
                    "real_send_enabled": self.server_state.real_send_enabled,
                    "pilot_enabled": self.server_state.automation_pilot,
                    "pilot_consumes_remaining": self.server_state.automation_pilot
                    and not self.server_state.automation_store.pilot_command_consumed(),
                },
            )
            return
        if parsed.path == "/api/v1/automation/capabilities":
            if not self._require_auth(allow_missing_origin=True):
                return
            self._send_automation_capabilities()
            return
        if parsed.path == "/api/v1/legal-context":
            if not self._require_auth(allow_missing_origin=True):
                return
            self._send_legal_context(parse_qs(parsed.query, keep_blank_values=True))
            return
        if parsed.path == "/review":
            if self._review_authorized():
                self._send_review_html()
            else:
                self._send_review_bootstrap()
            return
        if parsed.path == "/review-bootstrap.js":
            if not self._valid_host():
                self._error(403, "FORBIDDEN_HOST", "Host não permitido")
                return
            self._send_text(200, _REVIEW_BOOTSTRAP_JS, content_type="text/javascript; charset=utf-8", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
            return
        if parsed.path.startswith("/app/web/"):
            if not self._valid_host():
                self._error(403, "FORBIDDEN_HOST", "Host não permitido")
                return
            self._send_review_asset(unquote(parsed.path.removeprefix("/app/web/")))
            return
        if parsed.path == "/api/v1/review-data":
            if not self._require_private_auth(allow_missing_origin=True):
                return
            self._send_review_data(parse_qs(parsed.query))
            return
        if parsed.path.startswith("/api/v1/evidence/"):
            if not self._require_private_auth(allow_missing_origin=True):
                return
            self._send_evidence(unquote(parsed.path.removeprefix("/api/v1/evidence/")))
            return
        if parsed.path.startswith("/api/v1/pdf/"):
            if not self._require_private_auth(allow_missing_origin=True):
                return
            self._send_pdf(unquote(parsed.path.removeprefix("/api/v1/pdf/")))
            return
        if parsed.path == "/api/v1/state":
            if not self._require_private_auth():
                return
            params = parse_qs(parsed.query)
            try:
                since = int(params.get("since", ["-1"])[0])
            except ValueError:
                self._error(400, "INVALID_JSON", "since inválido")
                return
            snapshot = self.server_state.workflow_state.snapshot()
            self._send(200, {
                "api_version": API_VERSION,
                "revision": snapshot["revision"],
                "order": snapshot["process_keys"],
                "processes": snapshot["processes"],
                "selection": self.server_state.selection,
                "unchanged": since == snapshot["revision"],
            })
            return
        if not self._require_auth(allow_missing_origin=True):
            return
        process_list_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if parsed.path == "/api/v1/process-lists/active":
            try:
                active = self.server_state.process_lists.active()
            except ValueError as error:
                self._error(409, "ACTIVE_PROCESS_LIST_INVALID", str(error))
                return
            self._send(200, active if active is not None else {"active": None})
            return
        if len(process_list_parts) == 4 and process_list_parts[:3] == ["api", "v1", "process-lists"]:
            try:
                manifest = self.server_state.process_lists.load(process_list_parts[3])
            except ValueError:
                self._error(404, "PROCESS_LIST_NOT_FOUND", "lista de processos não encontrada")
                return
            self._send(200, manifest)
            return
        analysis_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if (
            len(analysis_parts) == 6
            and analysis_parts[:3] == ["api", "v1", "analysis"]
            and analysis_parts[4] == "acquire"
        ):
            self._send_analysis_acquisition_status(analysis_parts[3], analysis_parts[5])
            return
        if len(analysis_parts) == 4 and analysis_parts[:3] == ["api", "v1", "analysis"]:
            self._send_analysis(analysis_parts[3])
            return
        automation_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if automation_parts == ["api", "v1", "automation", "runs"]:
            self._send_automation_runs(parse_qs(parsed.query, keep_blank_values=True))
            return
        if len(automation_parts) == 6 and automation_parts[:3] == ["api", "v1", "automation"] and automation_parts[3] == "runs" and automation_parts[5] == "events":
            run_id = automation_parts[4]
            if not AUTOMATION_RUN_ID_RE.fullmatch(run_id):
                self._error(404, "RUN_NOT_FOUND", "execução não encontrada")
                return
            self._send_automation_events(run_id, parse_qs(parsed.query, keep_blank_values=True))
            return
        if len(automation_parts) == 5 and automation_parts[:3] == ["api", "v1", "automation"] and automation_parts[3] == "runs":
            run_id = automation_parts[4]
            if not AUTOMATION_RUN_ID_RE.fullmatch(run_id):
                self._error(404, "RUN_NOT_FOUND", "execução não encontrada")
                return
            self._send_automation_run(run_id)
            return
        if len(automation_parts) == 6 and automation_parts[:3] == ["api", "v1", "automation"] and automation_parts[3] == "runs" and automation_parts[5] == "report":
            run_id = automation_parts[4]
            if not AUTOMATION_RUN_ID_RE.fullmatch(run_id):
                self._error(404, "RUN_NOT_FOUND", "execução não encontrada")
                return
            self._send_automation_report(run_id, parse_qs(parsed.query, keep_blank_values=True))
            return
        if parsed.path == "/api/v1/dataset":
            self._send_dataset()
            return
        self._error(404, "NOT_FOUND", "rota não encontrada")

    def _send_dataset(self):
        try:
            publication = _current_publication_dataset(self.server_state.workflow_root)
        except (OSError, ValueError, json.JSONDecodeError):
            self._error(500, "PUBLICATION_INVALID", "ponteiro de publicação inválido")
            return
        path = publication[1] if publication is not None else _sidecar(self.server_state.workflow_root, "dados-complementar-ato.json")
        if path is None:
            self._error(404, "DATASET_NOT_FOUND", "dataset não encontrado")
            return
        try:
            dataset = _read_object(path)
        except (OSError, ValueError, json.JSONDecodeError):
            self._error(500, "DATASET_INVALID", "dataset inválido")
            return
        revision = publication[0] if publication is not None else self.server_state.service_revision
        self._send(200, {"api_version": API_VERSION, "revision": revision, "dataset": dataset})

    def _send_review_data(self, params: dict[str, list[str]]):
        try:
            since = int(params.get("since", ["-1"])[0])
        except (TypeError, ValueError):
            self._error(400, "INVALID_JSON", "since inválido")
            return
        try:
            publication = _current_publication_review(self.server_state.workflow_root)
        except (OSError, ValueError, json.JSONDecodeError):
            self._error(500, "PUBLICATION_INVALID", "ponteiro de publicação inválido")
            return
        if publication is None:
            self._error(404, "REVIEW_DATA_NOT_FOUND", "snapshot de revisão não encontrado")
            return
        revision, path = publication
        if since == revision:
            self._send(200, {"api_version": API_VERSION, "revision": revision, "unchanged": True})
            return
        try:
            data = _read_object(path)
        except (OSError, ValueError, json.JSONDecodeError):
            self._error(500, "REVIEW_DATA_INVALID", "snapshot de revisão inválido")
            return
        self._send(200, {"api_version": API_VERSION, "revision": revision, "unchanged": False, "data": self._review_payload_for_browser(data)})

    def _send_evidence(self, record_id: str):
        if not record_id or "/" in record_id or "\\" in record_id:
            self._error(404, "EVIDENCE_NOT_FOUND", "evidência não encontrada")
            return
        path = _sidecar(self.server_state.workflow_root, "evidencias-visuais.json")
        if path is None:
            self._error(404, "EVIDENCE_NOT_FOUND", "evidência não encontrada")
            return
        try:
            data = _read_object(path)
            record = data.get("records", {}).get(record_id)
        except (OSError, ValueError, json.JSONDecodeError):
            record = None
        if record is None:
            self._error(404, "EVIDENCE_NOT_FOUND", "evidência não encontrada")
            return
        self._send(200, {"api_version": API_VERSION, "record_id": record_id, "record": record, "documents": data.get("documents", {})})

    def _send_pdf(self, document_id: str):
        if not document_id or "/" in document_id or "\\" in document_id:
            self._error(404, "DOCUMENT_NOT_FOUND", "documento não encontrado")
            return
        path = _sidecar(self.server_state.workflow_root, "evidencias-visuais.json")
        if path is None:
            self._error(404, "DOCUMENT_NOT_FOUND", "documento não encontrado")
            return
        try:
            data = _read_object(path)
            entry = data.get("documents", {}).get(document_id)
            file_path = _safe_file(self.server_state.workflow_root, entry.get("relative_path") if isinstance(entry, dict) else None)
            if file_path is None or (isinstance(entry, dict) and entry.get("sha256") and entry["sha256"] != _sha256(file_path)):
                raise _DocumentNotFound
            payload = file_path.read_bytes()
        except _DocumentNotFound:
            self._error(404, "DOCUMENT_NOT_FOUND", "documento não encontrado")
            return
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            self._error(404, "DOCUMENT_NOT_FOUND", "documento não encontrado")
            return
        try:
            selected = _parse_range(self.headers.get("Range"), len(payload))
        except ValueError:
            self._send(416, {"error": {"code": "RANGE_INVALID", "message": "Range inválido"}}, headers={"Content-Range": f"bytes */{len(payload)}"})
            return
        if selected is None:
            self._send(200, body=payload, headers={"Content-Type": "application/pdf", "Accept-Ranges": "bytes"})
            return
        start, end = selected
        self._send(206, body=payload[start:end + 1], headers={
            "Content-Type": "application/pdf",
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{len(payload)}",
        })

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/v1/pair":
            if not self._valid_host():
                self._error(403, "FORBIDDEN_HOST", "Host não permitido")
                return
            origin = self.headers.get("Origin")
            if not self.server_state.auth.is_extension_origin(origin):
                self._error(403, "FORBIDDEN_ORIGIN", "Origin de extensão necessária")
                return
            try:
                payload = self._read_json()
                if set(payload) != {"code"} or not isinstance(payload["code"], str):
                    raise ValueError
                token = self.server_state.auth.redeem(payload["code"], origin)
            except (ValueError, UnicodeDecodeError):
                self._error(400, "INVALID_JSON", "JSON inválido")
                return
            except BridgeAuthError:
                self._error(401, "PAIRING_REJECTED", "pareamento rejeitado")
                return
            self._send(200, {"api_version": API_VERSION, "token": token})
            return
        if parsed.path == "/api/v1/review-session":
            if not self._valid_host() or self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
                self._error(403, "FORBIDDEN_ORIGIN", "origem local necessária")
                return
            try:
                payload = self._read_json()
                if set(payload) != {"code"} or not isinstance(payload["code"], str):
                    raise ValueError
                token, csrf_token = self.server_state.redeem_review_bootstrap(payload["code"])
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self._error(401, "REVIEW_SESSION_REJECTED", "código da mesa rejeitado")
                return
            self._send(
                200,
                {"api_version": API_VERSION, "authenticated": True, "csrf_token": csrf_token},
                headers={
                    "Set-Cookie": [
                        f"tce_review={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={8 * 60 * 60}",
                        f"tce_csrf={csrf_token}; SameSite=Strict; Path=/; Max-Age={8 * 60 * 60}",
                    ]
                },
            )
            return
        if not self._require_auth():
            return
        process_list_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if parsed.path == "/api/v1/process-lists/import":
            self._import_process_list()
            return
        if (
            len(process_list_parts) == 5
            and process_list_parts[:3] == ["api", "v1", "process-lists"]
            and process_list_parts[4] == "report"
        ):
            self._create_process_list_report(process_list_parts[3])
            return
        if parsed.path == "/api/v1/analysis/preview":
            self._create_analysis_preview()
            return
        analysis_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if (
            len(analysis_parts) == 5
            and analysis_parts[:3] == ["api", "v1", "analysis"]
            and analysis_parts[4] == "lots"
        ):
            self._create_analysis_lots(analysis_parts[3])
            return
        if (
            len(analysis_parts) == 5
            and analysis_parts[:3] == ["api", "v1", "analysis"]
            and analysis_parts[4] == "acquire"
        ):
            self._start_analysis_acquisition(analysis_parts[3])
            return
        if parsed.path == "/api/v1/automation/runs":
            try:
                payload = self._read_json()
                spec, event_id = _validate_run_payload(
                    payload,
                    pilot_enabled=self.server_state.automation_pilot,
                )
                created = self.server_state.automation_store.replay_run_creation(spec, event_id)
                if created is None:
                    auto_send_allowed = self.server_state.real_send_enabled or (
                        spec.get("mode", "batch") == "pilot" and self.server_state.automation_pilot
                    )
                    if spec.get("auto_submit") is True and not auto_send_allowed:
                        raise _ApiProblem(
                            409,
                            "REAL_SEND_DISABLED",
                            "auto_submit exige uma qualificação local válida e ativação explícita",
                        )
                    _revision, _dataset, computed = _load_current_dataset(self.server_state.workflow_root)
                    if spec["dataset_sha256"] != computed:
                        raise _ApiProblem(409, "DATASET_MISMATCH", "dataset_sha256 não corresponde ao dataset atual")
                    created = self.server_state.automation_store.create_run(spec, event_id)
                result = _project_automation_snapshot(created, created["run_id"])
            except _ApiProblem as problem:
                self._error(problem.status, problem.code, str(problem))
                return
            except _BodyTooLarge as problem:
                self._error(problem.status, problem.code, str(problem))
                return
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                self._error(400, "INVALID_JSON", "JSON inválido")
                return
            except Exception as error:
                problem = _automation_store_error(error)
                self._error(problem.status, problem.code, str(problem))
                return
            self._send(200, result)
            return

        command_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if (
            len(command_parts) == 8
            and command_parts[:3] == ["api", "v1", "automation"]
            and command_parts[3] == "runs"
            and command_parts[5] == "commands"
            and command_parts[7] == "consume"
        ):
            run_id = command_parts[4]
            command_id = command_parts[6]
            if not AUTOMATION_RUN_ID_RE.fullmatch(run_id) or not AUTOMATION_ID_RE.fullmatch(command_id):
                self._error(404, "NOT_FOUND", "comando não encontrado")
                return
            try:
                payload = self._read_json()
                expected_revision = _validate_command_consume_payload(payload)
                run_snapshot = self.server_state.automation_store.snapshot(run_id)
                run_mode = run_snapshot.get("spec", {}).get("mode", "batch")
                if run_mode == "pilot":
                    if not self.server_state.automation_pilot:
                        raise _ApiProblem(
                            409,
                            "REAL_SEND_DISABLED",
                            "envio real está desabilitado; use somente o piloto explicitamente qualificado",
                        )
                    enforce_pilot_budget = True
                elif not self.server_state.real_send_enabled:
                    raise _ApiProblem(
                        409,
                        "REAL_SEND_DISABLED",
                        "envio em lote exige uma qualificação local válida e ativação explícita",
                    )
                else:
                    enforce_pilot_budget = False
                consumed = self.server_state.automation_store.consume_command(
                    run_id,
                    command_id,
                    expected_revision,
                    enforce_pilot_budget=enforce_pilot_budget,
                )
                snapshot = _project_automation_snapshot(consumed, run_id)
                result = {
                    "api_version": API_VERSION,
                    "dispatch_allowed": consumed["dispatch_allowed"],
                    "command_id": consumed["command_id"],
                    **snapshot,
                }
            except _ApiProblem as problem:
                self._error(problem.status, problem.code, str(problem))
                return
            except _BodyTooLarge as problem:
                self._error(problem.status, problem.code, str(problem))
                return
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self._error(400, "INVALID_JSON", "JSON inválido")
                return
            except Exception as error:
                problem = _automation_store_error(error)
                self._error(problem.status, problem.code, str(problem))
                return
            self._send(200, result)
            return

        automation_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(automation_parts) == 6 and automation_parts[:3] == ["api", "v1", "automation"] and automation_parts[3] == "runs":
            run_id = automation_parts[4]
            route = automation_parts[5]
            if not AUTOMATION_RUN_ID_RE.fullmatch(run_id) or route not in {"queue", "events", "control"}:
                self._error(404, "NOT_FOUND", "rota não encontrada")
                return
            try:
                payload = self._read_json()
                current = self.server_state.automation_store.snapshot(run_id)
                if route == "queue":
                    identities, event_id, expected_revision = _validate_queue_payload(payload)
                    replay = self.server_state.automation_store.replay_queue(run_id, identities, event_id)
                    if replay is not None:
                        updated = replay
                    else:
                        dataset, dataset_sha256 = self._assert_run_dataset(current)
                        for identity in identities:
                            if _dataset_record(dataset, identity["process_key"], identity["interested_normalized"]) is None:
                                raise _ApiProblem(409, "IDENTITY_NOT_IN_DATASET", "identidade não pertence ao dataset atual")
                            if (self.server_state.workflow_root / "fundamentos-contexto.v1.json").is_file():
                                try:
                                    _load_context_record(
                                        self.server_state.workflow_root,
                                        identity["process_key"],
                                        identity["interested_normalized"],
                                        dataset_sha256,
                                    )
                                except _ApiProblem as problem:
                                    if problem.code == "LEGAL_CONTEXT_NOT_FOUND":
                                        raise _ApiProblem(409, "LEGAL_CONTEXT_NOT_FOUND", "identidade sem contexto jurídico exato") from problem
                                    raise
                        updated = self.server_state.automation_store.freeze_queue(
                            run_id, identities, event_id, expected_revision
                        )
                elif route == "events":
                    event = _validate_event_input(payload)
                    store_event = {
                        "event_id": event["event_id"],
                        "expected_revision": event["expected_revision"],
                        "type": event["type"],
                        "payload": event["payload"],
                    }
                    if event["item_id"] is not None:
                        store_event["item_id"] = event["item_id"]
                    updated = self.server_state.automation_store.append_event(run_id, store_event)
                    if event["type"] == "send_confirmed":
                        try:
                            render_run_reports(
                                self.server_state.automation_store,
                                run_id,
                                self.server_state.workflow_root,
                            )
                        except Exception as error:
                            raise _ApiProblem(
                                500,
                                "REPORT_UPDATE_FAILED",
                                "relatório não pôde ser atualizado antes do próximo ato",
                            ) from error
                else:
                    action, control = _validate_control_payload(payload)
                    event_type = {
                        "pause": "run_paused",
                        "resume": "run_resumed",
                        "stop": "run_stopped",
                    }[action]
                    updated = self.server_state.automation_store.append_event(
                        run_id,
                        {
                            "event_id": control["event_id"],
                            "expected_revision": control["expected_revision"],
                            "type": event_type,
                            "payload": {},
                        },
                    )
                result = _project_automation_snapshot(updated, run_id)
            except _ApiProblem as problem:
                self._error(problem.status, problem.code, str(problem))
                return
            except _BodyTooLarge as problem:
                self._error(problem.status, problem.code, str(problem))
                return
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                self._error(400, "INVALID_JSON", "JSON inválido")
                return
            except Exception as error:
                problem = _automation_store_error(error)
                self._error(problem.status, problem.code, str(problem))
                return
            self._send(200, result)
            return
        if parsed.path == "/api/v1/selection":
            try:
                payload = self._read_json()
                if set(payload) != {"process_key", "interested_normalized", "tab_id", "frame_id", "sequence"}:
                    raise ValueError
                if not isinstance(payload["process_key"], str) or not isinstance(payload["interested_normalized"], str) or not all(type(payload[key]) is int for key in ("tab_id", "frame_id", "sequence")):
                    raise ValueError
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self._error(400, "INVALID_JSON", "seleção inválida")
                return
            if payload["tab_id"] < 0 or payload["frame_id"] < 0 or payload["sequence"] <= 0:
                self._error(400, "INVALID_SELECTION", "tab_id, frame_id e sequence devem ser válidos")
                return
            previous = self.server_state.selection
            if previous is not None and payload["sequence"] <= previous["sequence"]:
                self._send(200, {"accepted": False, "sequence": previous["sequence"], "discarded_sequence": payload["sequence"]})
                return
            self.server_state.selection = payload
            self.server_state.service_revision += 1
            self._send(200, {"accepted": True, "revision": self.server_state.service_revision})
            return
        self._error(404, "NOT_FOUND", "rota não encontrada")

    def do_PUT(self):
        parsed = urlsplit(self.path)
        if not self._require_private_mutation_auth():
            return
        if not parsed.path.startswith("/api/v1/progress/"):
            self._error(404, "NOT_FOUND", "rota não encontrada")
            return
        process_key = unquote(parsed.path.removeprefix("/api/v1/progress/"))
        try:
            payload = self._read_json()
            if set(payload) != {"completed", "expected_revision"} or type(payload["completed"]) is not bool or type(payload["expected_revision"]) is not int:
                raise ValueError
            result = self.server_state.workflow_state.set_completed(process_key, payload["completed"], payload["expected_revision"])
        except RevisionConflict as exc:
            self._error(409, "REVISION_CONFLICT", str(exc))
            return
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            self._error(400, "INVALID_JSON", "progresso inválido")
            return
        self._send(200, {"api_version": API_VERSION, "revision": result["revision"], "state": result})


def create_server(
    root: Path,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    *,
    automation_pilot: bool = False,
    enable_real_send: bool = False,
):
    if host != "127.0.0.1":
        raise ValueError("o serviço deve usar 127.0.0.1")
    if not isinstance(port, int) or port < 0 or port > 65535:
        raise ValueError("porta inválida")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidates = (port,) if port == 0 else (port, *FALLBACK_PORTS)
    last_error = None
    for candidate in candidates:
        try:
            server = _WorkflowHTTPServer(
                (host, candidate),
                root,
                automation_pilot=automation_pilot,
                enable_real_send=enable_real_send,
            )
            return server
        except OSError as exc:
            last_error = exc
        except Exception:
            raise
    raise OSError(f"não foi possível abrir porta loopback: {last_error}")


def _write_runtime_metadata(path: Path, server: _WorkflowHTTPServer) -> dict[str, object]:
    pairing_code = server.auth.issue_pairing_code()
    review_code = server.review_bootstrap_code
    metadata = {
        "schema_version": 1,
        "pid": os.getpid(),
        "port": server.server_port,
        "executable": str(Path(os.environ.get("PYTHONEXECUTABLE", os.sys.executable)).resolve()),
        "started_at": time.time(),
        "pairing_code": pairing_code,
        "review_url": f"http://127.0.0.1:{server.server_port}/review#bootstrap={quote(review_code or '', safe='')}" if review_code else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(metadata, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="serviço local autenticado do pacote portátil")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bridge-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--automation-pilot", action="store_true")
    parser.add_argument("--enable-real-send", action="store_true")
    args = parser.parse_args(argv)
    package_root = args.root.resolve().parent
    operation_lock_path, operation_lock_token = _acquire_operation_lock(package_root)
    server = None
    try:
        if transfer_requested(package_root):
            raise RuntimeError("transferência em andamento; serviço local aguardará a conclusão")
        active = _active_runtime(package_root)
        if active is not None:
            raise RuntimeError(
                f"execução ativa ({active}); serviço local não será iniciado"
            )
        server = create_server(
            args.root,
            host=args.host,
            port=args.port,
            automation_pilot=args.automation_pilot,
            enable_real_send=args.enable_real_send,
        )
        metadata_path = args.bridge_root / "service.json"
        _write_runtime_metadata(metadata_path, server)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            f"Serviço local indisponível; modo manual preservado: {exc}",
            file=sys.stderr,
        )
        return 2
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
            try:
                metadata_path.unlink()
            except FileNotFoundError:
                pass
        _release_operation_lock(operation_lock_path, operation_lock_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
