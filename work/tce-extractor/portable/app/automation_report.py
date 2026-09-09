"""Atomic, sanitized HTML and CSV reports for automation runs."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
from io import StringIO
import tempfile
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from automation_store import AutomationStore


_SENSITIVE_KEY_PARTS = frozenset(
    {
        "token",
        "cookie",
        "password",
        "passwd",
        "secret",
        "credential",
        "authorization",
        "csrf",
        "cpf",
        "session",
        "sessionid",
        "sid",
        "url",
        "path",
        "filename",
        "file",
        "api_key",
        "apikey",
    }
)
_EVENT_PAYLOAD_ALLOWLIST = frozenset(
    {
        "item_id",
        "item_key",
        "process_key",
        "act_id",
        "identity",
        "identities",
        "fields",
        "field_results",
        "before",
        "after",
        "method",
        "source",
        "origin",
        "rereads",
        "re_read",
        "legal_decision",
        "decision",
        "citations",
        "timestamp",
        "error",
        "errors",
        "reason",
    }
)
_IDENTITY_KEYS = frozenset({"item_id", "process_key", "id", "key", "act_id"})
_CITATION_KEYS = frozenset({"document_id", "page_id", "page", "label"})
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9._:/-]{1,256}")
_PROCESS_KEY_RE = re.compile(r"\d+/\d{4}")
_URL_RE = re.compile(
    r"(?:\b(?:https?|wss?|ftp|file|mailto|javascript|data):[^\s<>'\"]+"
    r"|(?<!\w)//[^\s<>'\"]+|\bwww\.[^\s<>'\"]+"
    r"|(?<![@\w])(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:/[^\s<>'\"]*)?)",
    re.IGNORECASE,
)
_CPF_RE = re.compile(
    r"(?:"
    r"(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}(?!\d)"
    r"|(?<!\d)\d{10}(?!\d)"
    r")"
)
_TOKEN_RE = re.compile(
    r"(?:\bBearer\s+[A-Za-z0-9._~+/=-]+"
    r"|\b(?:access|auth|refresh|session|id|csrf)?[_-]?token\s*[:=]\s*[^\s,;]+"
    r"|\b(?:api|x[-_]?api|client)[-_]?(?:key|secret)\s*[:=]\s*[^\s,;]+"
    r"|\bauthorization\s*[:=]\s*(?:Bearer\s+)?[^\s,;]+)",
    re.IGNORECASE,
)
_COOKIE_HEADER_RE = re.compile(
    r"\b(?:cookie|set-cookie)\s*[:=\s]*[^\r\n]+", re.IGNORECASE
)
_COOKIE_PAIR_RE = re.compile(
    r"\b(?:sid|session|sessionid|session_id|csrftoken|csrf_token|connect\.sid|"
    r"auth(?:entication)?[_-]?cookie)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE, )
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\|/)[^<>\"'\s;,]+"
)
_RELATIVE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\.\.?[\\/]|(?:[A-Za-z0-9_. -]+[\\/])+)[^<>\"'\s;,]+"
)
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _normalized_key(key: str) -> str:
    camel_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return re.sub(r"[^a-z0-9]+", "_", camel_case.casefold()).strip("_")


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalized_key(key)
    if not normalized:
        return False
    return bool(_SENSITIVE_KEY_PARTS.intersection(normalized.split("_")))


def _redact_text(value: str) -> str:
    value = _COOKIE_HEADER_RE.sub("[redacted-cookie]", value)
    value = _COOKIE_PAIR_RE.sub("[redacted-cookie]", value)
    value = _URL_RE.sub("[redacted-url]", value)
    value = _TOKEN_RE.sub("[redacted-token]", value)
    value = _JWT_RE.sub("[redacted-token]", value)
    value = _CPF_RE.sub("[redacted-cpf]", value)
    value = _ABSOLUTE_PATH_RE.sub("[redacted-path]", value)
    return _RELATIVE_PATH_RE.sub("[redacted-path]", value)


def _is_allowed_process_key(value: Any, key: str) -> bool:
    return (
        key in {"item_id", "process_key"}
        and isinstance(value, str)
        and _PROCESS_KEY_RE.fullmatch(value) is not None
    )


def _safe_identifier(value: Any, key: str = "") -> str:
    if isinstance(value, bool):
        return "[redacted-id]"
    if isinstance(value, int):
        if 10**9 <= abs(value) <= 10**11 - 1:
            return "[redacted-id]"
        text = str(value)
    elif isinstance(value, str):
        text = value if _is_allowed_process_key(value, key) else _redact_text(value)
    else:
        return "[redacted-id]"
    if _SAFE_ID_RE.fullmatch(text):
        return text
    return "[redacted-id]"


def _safe_citation_object(value: Any) -> dict[str, str | int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str | int] = {}
    for key in _CITATION_KEYS:
        if key not in value:
            continue
        candidate = value[key]
        if key in {"document_id", "page_id"}:
            safe = _safe_identifier(candidate)
            if safe != "[redacted-id]":
                result[key] = safe
        elif key == "page":
            if (
                isinstance(candidate, int)
                and not isinstance(candidate, bool)
                and 0 <= candidate <= 999999
            ) or (isinstance(candidate, str) and re.fullmatch(r"\d{1,6}", candidate)):
                result[key] = candidate
        elif key == "label" and isinstance(candidate, str):
            label = _redact_text(candidate).strip()
            if label and all(character.isprintable() for character in label):
                result[key] = label[:256]
    if not any(key in result for key in ("document_id", "page_id")):
        return {}
    return result


def _safe_identity(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_identifier(value[key], key)
            for key in _IDENTITY_KEYS
            if key in value and _safe_identifier(value[key], key) != "[redacted-id]"
        }
    if isinstance(value, list):
        return [_safe_identity(item) for item in value]
    return _safe_identifier(value)


def _safe_snapshot_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    if "identity" in value:
        result["identity"] = _safe_identity(value["identity"])
    for key in ("ordinal", "state", "created_at", "updated_at"):
        if key in value:
            result[key] = _safe_value(value[key], key)
    return result


def _safe_last_confirmed(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    identity_key = value.get("identity_key")
    if isinstance(identity_key, str):
        try:
            result["identity"] = _safe_identity(json.loads(identity_key))
        except json.JSONDecodeError:
            pass
    if isinstance(value.get("payload"), dict):
        result["payload"] = _safe_event_payload(value["payload"])
    if "confirmed_at" in value:
        result["confirmed_at"] = _safe_value(value["confirmed_at"], "timestamp")
    return result


def _safe_value(value: Any, key: str = "", depth: int = 0) -> Any:
    if depth > 12:
        return "[redacted-depth]"
    if key and _is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(child_key): _safe_value(child, str(child_key), depth + 1)
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(child, key, depth + 1) for child in value]
    if isinstance(value, tuple):
        return [_safe_value(child, key, depth + 1) for child in value]
    if isinstance(value, str):
        if _is_allowed_process_key(value, key):
            return value
        return _redact_text(value)
    if isinstance(value, int) and not isinstance(value, bool) and 10**9 <= abs(value) <= 10**11 - 1:
        return "[redacted-cpf]"
    if isinstance(value, float) and value.is_integer() and 10**9 <= abs(value) <= 10**11 - 1:
        return "[redacted-cpf]"
    return value


def _safe_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in _EVENT_PAYLOAD_ALLOWLIST:
        if key not in payload:
            continue
        value = payload[key]
        if key in {"identity", "identities"}:
            safe[key] = _safe_identity(value)
        elif key == "citations":
            if not isinstance(value, list):
                continue
            safe[key] = [
                citation
                for item in value
                if isinstance(item, dict)
                for citation in [_safe_citation_object(item)]
                if citation
            ]
        elif key in _IDENTITY_KEYS:
            safe[key] = _safe_identifier(value, key)
        else:
            safe[key] = _safe_value(value, key)
    return safe


def _display(value: Any, key: str = "") -> str:
    safe = _safe_value(value, key)
    if safe is None:
        return ""
    if isinstance(safe, (dict, list)):
        return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(safe)


def _citation(value: Any) -> str:
    safe = _safe_citation_object(value)
    if not safe:
        return "[redacted-citation]"
    parts = [
        str(safe[key])
        for key in ("document_id", "page_id")
        if key in safe
    ]
    if "page" in safe:
        parts.append(f"p.{safe['page']}")
    if "label" in safe:
        parts.append(str(safe["label"]))
    return " ".join(parts) or "[redacted-citation]"


def _citations(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "; ".join(_citation(item) for item in value)


def _item_label(payload: dict[str, Any]) -> str:
    for key in ("item_id", "item_key", "process_key", "act_id", "identity"):
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, dict):
            for identity_key in ("item_id", "process_key", "id", "key", "act_id"):
                if identity_key in value:
                    return _display(value[identity_key], identity_key)
        return _display(value, key)
    return ""


def _field_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    default_method = payload.get("method", "")
    default_source = payload.get("source", payload.get("origin", ""))
    rows: list[dict[str, Any]] = []

    fields = payload.get("fields")
    if isinstance(fields, dict):
        for field_name, value in fields.items():
            if isinstance(value, dict):
                rows.append(
                    {
                        "field": str(field_name),
                        "before": value.get("before"),
                        "after": value.get("after", value.get("value")),
                        "method": value.get("method", default_method),
                        "source": value.get("source", value.get("origin", default_source)),
                    }
                )
            else:
                rows.append(
                    {
                        "field": str(field_name),
                        "before": None,
                        "after": value,
                        "method": default_method,
                        "source": default_source,
                    }
                )

    field_results = payload.get("field_results")
    if isinstance(field_results, list):
        for value in field_results:
            if isinstance(value, dict):
                rows.append(
                    {
                        "field": str(value.get("field", value.get("name", ""))),
                        "before": value.get("before"),
                        "after": value.get("after", value.get("value")),
                        "method": value.get("method", default_method),
                        "source": value.get("source", value.get("origin", default_source)),
                    }
                )

    if not rows:
        before = payload.get("before")
        after = payload.get("after")
        if isinstance(before, dict) or isinstance(after, dict):
            before_dict = before if isinstance(before, dict) else {}
            after_dict = after if isinstance(after, dict) else {}
            for field_name in sorted(set(before_dict) | set(after_dict)):
                rows.append(
                    {
                        "field": str(field_name),
                        "before": before_dict.get(field_name),
                        "after": after_dict.get(field_name),
                        "method": default_method,
                        "source": default_source,
                    }
                )

    if not rows:
        rows.append(
            {
                "field": "",
                "before": before if "before" in locals() else "",
                "after": after if "after" in locals() else "",
                "method": default_method,
                "source": default_source,
            }
        )
    return rows


def _report_rows(run_id: str, events: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        payload = _safe_event_payload(payload)
        item_id = _item_label(payload)
        rereads = _display(payload.get("rereads", payload.get("re_read", [])))
        legal_decision = _display(payload.get("legal_decision", payload.get("decision", {})))
        citations = _citations(payload.get("citations", []))
        timestamp = _display(payload.get("timestamp", event.get("created_at", "")))
        error = _display(payload.get("error", payload.get("errors", "")))
        for field in _field_rows(payload):
            result.append(
                {
                    "run_id": run_id,
                    "seq": str(event.get("seq", "")),
                    "event_id": _display(event.get("event_id", "")),
                    "event_type": _display(event.get("type", "")),
                    "item_id": item_id,
                    "field": _display(field["field"]),
                    "before": _display(field["before"]),
                    "after": _display(field["after"]),
                    "method": _display(field["method"]),
                    "source": _display(field["source"]),
                    "rereads": rereads,
                    "legal_decision": legal_decision,
                    "citations": citations,
                    "timestamp": timestamp,
                    "error": error,
                }
            )
    return result


def _csv_cell(value: object, key: str = "") -> str:
    text = _display(value, key)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _html_value(value: object, key: str = "") -> str:
    return html.escape(_display(value, key), quote=True)


def _render_html(
    snapshot: dict[str, Any], events: list[dict[str, Any]], rows: list[dict[str, str]]
) -> str:
    last_confirmed = _safe_last_confirmed(snapshot.get("last_confirmed"))
    interrupted = _safe_snapshot_item(snapshot.get("interrupted_item"))
    parts = [
        "<!doctype html>",
        '<html lang="pt-BR"><head><meta charset="utf-8">',
        f"<title>Relatório de complementação — {_html_value(snapshot['run_id'])}</title>",
        "</head><body>",
        "<h1>Relatório de complementação</h1>",
        f"<p>Execução: <code>{_html_value(snapshot['run_id'])}</code></p>",
        f"<p>Estado: {_html_value(snapshot.get('state'))} · revisão: {_html_value(snapshot.get('revision'))}</p>",
        f"<p>Início: {_html_value(snapshot.get('started_at'))} · atualização: {_html_value(snapshot.get('updated_at'))}</p>",
        f"<h2>Último confirmado</h2><pre>{_html_value(last_confirmed or 'nenhum')}</pre>",
        f"<h2>Item interrompido</h2><pre>{_html_value(interrupted or 'nenhum')}</pre>",
        "<h2>Eventos</h2>",
    ]
    if not events:
        parts.append("<p>nenhum evento</p>")
    for event in events:
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        payload = _safe_event_payload(payload)
        parts.extend(
            [
                "<article>",
                f"<h3>#{_html_value(event.get('seq'))} {_html_value(event.get('type'))}</h3>",
                f"<p>event_id: <code>{_html_value(event.get('event_id'))}</code> · "
                f"timestamp: {_html_value(payload.get('timestamp', event.get('created_at')) if isinstance(payload, dict) else event.get('created_at'))}</p>",
                f"<pre>{_html_value(payload)}</pre>",
                "</article>",
            ]
        )
    parts.extend(
        [
            "<h2>Atos e campos</h2>",
            '<table><thead><tr><th>Ato</th><th>Campo</th><th>Antes</th><th>Depois</th>'
            "<th>Método</th><th>Origem</th><th>Relidos</th><th>Decisão jurídica</th>"
            "<th>Citações</th><th>Timestamp</th><th>Erro</th></tr></thead><tbody>",
        ]
    )
    for row in rows:
        parts.append(
            "<tr>"
            + "".join(
                f"<td>{_html_value(row[column], column)}</td>"
                for column in (
                    "item_id",
                    "field",
                    "before",
                    "after",
                    "method",
                    "source",
                    "rereads",
                    "legal_decision",
                    "citations",
                    "timestamp",
                    "error",
                )
            )
            + "</tr>"
        )
    parts.extend(["</tbody></table>", "</body></html>", ""])
    return "\n".join(parts)


def _render_csv(rows: list[dict[str, str]]) -> str:
    columns = [
        "run_id",
        "seq",
        "event_id",
        "event_type",
        "item_id",
        "field",
        "before",
        "after",
        "method",
        "source",
        "rereads",
        "legal_decision",
        "citations",
        "timestamp",
        "error",
    ]
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {column: _csv_cell(row.get(column, ""), column) for column in columns}
        )
    return stream.getvalue()


def _stage(path: Path, content: str) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return Path(temporary_name)


def _stage_bytes(path: Path, content: bytes) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return Path(temporary_name)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generation_id(html_digest: str, csv_digest: str) -> str:
    return hashlib.sha256(f"{html_digest}:{csv_digest}".encode("ascii")).hexdigest()


def _validate_generation_directory(
    generation_directory: Path, html_digest: str, csv_digest: str
) -> None:
    html_path = generation_directory / "relatorio.html"
    csv_path = generation_directory / "relatorio.csv"
    if (
        not generation_directory.is_dir()
        or not html_path.is_file()
        or not csv_path.is_file()
    ):
        raise OSError("geração de relatório ausente ou incompleta")
    try:
        actual_html_digest = _sha256_file(html_path)
        actual_csv_digest = _sha256_file(csv_path)
    except OSError as exc:
        raise OSError("não foi possível validar a geração do relatório") from exc
    if actual_html_digest != html_digest or actual_csv_digest != csv_digest:
        raise OSError("hash divergente na geração do relatório")


def _validate_published_manifest(manifest_path: Path) -> None:
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OSError("manifesto de relatório inválido") from exc
    if not isinstance(manifest, dict):
        raise OSError("manifesto de relatório inválido")
    generation = manifest.get("generation")
    if not isinstance(generation, str) or not re.fullmatch(r"[0-9a-f]{64}", generation):
        raise OSError("geração inválida no manifesto de relatório")
    expected_html_path = f".generations/{generation}/relatorio.html"
    expected_csv_path = f".generations/{generation}/relatorio.csv"
    if (
        manifest.get("html_path") != expected_html_path
        or manifest.get("csv_path") != expected_csv_path
        or not isinstance(manifest.get("html_sha256"), str)
        or not isinstance(manifest.get("csv_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", manifest.get("html_sha256", ""))
        or not re.fullmatch(r"[0-9a-f]{64}", manifest.get("csv_sha256", ""))
    ):
        raise OSError("ponteiro ou hash inválido no manifesto de relatório")
    if generation != _generation_id(manifest["html_sha256"], manifest["csv_sha256"]):
        raise OSError("geração divergente dos hashes do manifesto")
    generation_directory = manifest_path.parent / ".generations" / generation
    _validate_generation_directory(
        generation_directory,
        manifest["html_sha256"],
        manifest["csv_sha256"],
    )
    for filename, digest_key in (
        ("relatorio.html", "html_sha256"),
        ("relatorio.csv", "csv_sha256"),
    ):
        compatibility_path = manifest_path.parent / filename
        if not compatibility_path.is_file() or _sha256_file(compatibility_path) != manifest[digest_key]:
            raise OSError("publicação compatível divergente do manifesto")


def _restore_replaced(
    backups: dict[Path, Path],
    replaced: list[Path],
) -> OSError | None:
    restore_error: OSError | None = None
    for path in reversed(replaced):
        try:
            backup = backups.get(path)
            if backup is None:
                path.unlink(missing_ok=True)
            else:
                os.replace(backup, path)
        except OSError as exc:
            restore_error = restore_error or exc
    return restore_error


def _publish_pair_with_manifest(
    paths_and_temps: list[tuple[Path, Path]],
    manifest_path: Path,
    manifest_content: str,
) -> None:
    previous = {
        path: path.read_bytes() if path.exists() else None
        for path, _temporary in paths_and_temps
    }
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    manifest_temp: Path | None = None
    restore_error: OSError | None = None
    try:
        for path, temporary in paths_and_temps:
            old = previous[path]
            if old is not None:
                backups[path] = _stage_bytes(path, old)
            os.replace(temporary, path)
            replaced.append(path)
        manifest_temp = _stage(manifest_path, manifest_content)
        os.replace(manifest_temp, manifest_path)
        _fsync_directory(manifest_path.parent)
    except Exception as exc:
        restore_error = _restore_replaced(backups, replaced)
        if restore_error is not None:
            raise OSError("falha ao restaurar publicação anterior") from restore_error
        raise exc
    finally:
        for _path, temporary in paths_and_temps:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        if manifest_temp is not None:
            try:
                manifest_temp.unlink(missing_ok=True)
            except OSError:
                pass
        if restore_error is None:
            for backup in backups.values():
                try:
                    backup.unlink(missing_ok=True)
                except OSError:
                    pass


def _stage_generation(
    generations_directory: Path,
    generation_id: str,
    html_content: str,
    csv_content: str,
) -> tuple[Path, bool]:
    generations_directory.mkdir(parents=True, exist_ok=True)
    generation_directory = generations_directory / generation_id
    if generation_directory.is_dir():
        _validate_generation_directory(
            generation_directory,
            hashlib.sha256(html_content.encode("utf-8")).hexdigest(),
            hashlib.sha256(csv_content.encode("utf-8")).hexdigest(),
        )
        return generation_directory, False
    if generation_directory.exists():
        raise OSError("caminho de geração existente não é um diretório")

    temporary_directory = Path(
        tempfile.mkdtemp(prefix=f".{generation_id}.", dir=generations_directory)
    )
    try:
        html_temp = _stage(temporary_directory / "relatorio.html", html_content)
        csv_temp = _stage(temporary_directory / "relatorio.csv", csv_content)
        os.replace(html_temp, temporary_directory / "relatorio.html")
        os.replace(csv_temp, temporary_directory / "relatorio.csv")
        _fsync_directory(temporary_directory)
        os.replace(temporary_directory, generation_directory)
        temporary_directory = Path()
        _fsync_directory(generations_directory)
        return generation_directory, True
    finally:
        if str(temporary_directory) not in {"", "."}:
            try:
                shutil.rmtree(temporary_directory)
            except OSError:
                pass


def render_run_reports(
    store: "AutomationStore", run_id: str, output_root: Path
) -> dict[str, Any]:
    """Render deterministic reports without changing the store."""

    snapshot = store.snapshot(run_id)
    events = store.get_events(run_id, through=snapshot["revision"])
    report_directory = Path(output_root) / "relatorios" / "complementacao" / snapshot["run_id"]
    report_directory.mkdir(parents=True, exist_ok=True)
    html_path = report_directory / "relatorio.html"
    csv_path = report_directory / "relatorio.csv"
    manifest_path = report_directory / "relatorio.manifest.json"
    generations_directory = report_directory / ".generations"
    _validate_published_manifest(manifest_path)
    rows = _report_rows(snapshot["run_id"], events)
    html_content = _render_html(snapshot, events, rows)
    csv_content = _render_csv(rows)
    html_digest = hashlib.sha256(html_content.encode("utf-8")).hexdigest()
    csv_digest = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
    generation_id = _generation_id(html_digest, csv_digest)
    manifest_content = (
        json.dumps(
            {
                "schema_version": 1,
                "run_id": snapshot["run_id"],
                "revision": snapshot["revision"],
                "event_count": len(events),
                "generation": generation_id,
                "html_path": f".generations/{generation_id}/relatorio.html",
                "csv_path": f".generations/{generation_id}/relatorio.csv",
                "html_sha256": html_digest,
                "csv_sha256": csv_digest,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    html_temp: Path | None = None
    csv_temp: Path | None = None
    generation_directory: Path | None = None
    generation_created = False
    published = False
    try:
        generation_directory, generation_created = _stage_generation(
            generations_directory,
            generation_id,
            html_content,
            csv_content,
        )
        html_temp = _stage(html_path, html_content)
        csv_temp = _stage(csv_path, csv_content)
        _publish_pair_with_manifest(
            [(html_path, html_temp), (csv_path, csv_temp)],
            manifest_path,
            manifest_content,
        )
        published = True
    finally:
        for temporary in (html_temp, csv_temp):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        if generation_created and generation_directory is not None:
            if not published:
                try:
                    shutil.rmtree(generation_directory)
                except OSError:
                    pass
    return {
        "run_id": snapshot["run_id"],
        "revision": snapshot["revision"],
        "event_count": len(events),
        "html_path": str(html_path),
        "csv_path": str(csv_path),
        "manifest_path": str(manifest_path),
        "generation": generation_id,
    }
