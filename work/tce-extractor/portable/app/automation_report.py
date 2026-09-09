"""Atomic, sanitized HTML and CSV reports for automation runs."""

from __future__ import annotations

import csv
import html
import json
import os
from pathlib import Path
import re
from io import StringIO
import tempfile
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from automation_store import AutomationStore


_SENSITIVE_KEY_RE = re.compile(
    r"(?:token|cookie|password|passwd|secret|credential|authorization|csrf|cpf|"
    r"session|url|path|filename|file_path)",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_CPF_RE = re.compile(r"(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}(?!\d)")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _redact(value: Any, key: str = "") -> Any:
    if key and _SENSITIVE_KEY_RE.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(child_key): _redact(child, str(child_key)) for child_key, child in value.items()}
    if isinstance(value, list):
        return [_redact(child, key) for child in value]
    if isinstance(value, tuple):
        return [_redact(child, key) for child in value]
    if isinstance(value, str):
        value = _URL_RE.sub("[redacted-url]", value)
        return _CPF_RE.sub("[redacted-cpf]", value)
    return value


def _display(value: Any) -> str:
    safe = _redact(value)
    if safe is None:
        return ""
    if isinstance(safe, (dict, list)):
        return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(safe)


def _citation(value: Any) -> str:
    if not isinstance(value, dict):
        return "[redacted-citation]"
    document = value.get("document_id", value.get("document"))
    page = value.get("page", value.get("page_number"))
    if not isinstance(document, str) or not document.strip():
        return "[redacted-citation]"
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", document):
        return "[redacted-citation]"
    if isinstance(page, bool) or not isinstance(page, (int, str)):
        return document
    page_text = str(page)
    if not re.fullmatch(r"\d{1,6}", page_text):
        return document
    return f"{document}:p.{page_text}"


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
                    return _display(value[identity_key])
        return _display(value)
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


def _csv_cell(value: object) -> str:
    text = _display(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _html_value(value: object) -> str:
    return html.escape(_display(value), quote=True)


def _render_html(
    snapshot: dict[str, Any], events: list[dict[str, Any]], rows: list[dict[str, str]]
) -> str:
    last_confirmed = snapshot.get("last_confirmed")
    interrupted = snapshot.get("interrupted_item")
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
                f"<td>{_html_value(row[column])}</td>"
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
        writer.writerow({column: _csv_cell(row.get(column, "")) for column in columns})
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


def _replace_pair(paths_and_temps: list[tuple[Path, Path]]) -> None:
    previous = {
        path: path.read_bytes() if path.exists() else None
        for path, _temporary in paths_and_temps
    }
    replaced: list[Path] = []
    try:
        for path, temporary in paths_and_temps:
            os.replace(temporary, path)
            replaced.append(path)
    except Exception:
        for path in replaced:
            old = previous[path]
            try:
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(old)
            except OSError:
                pass
        raise
    finally:
        for _path, temporary in paths_and_temps:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def render_run_reports(
    store: "AutomationStore", run_id: str, output_root: Path
) -> dict[str, Any]:
    """Render deterministic reports without changing the store."""

    snapshot = store.snapshot(run_id)
    events = store.get_events(run_id)
    report_directory = Path(output_root) / "relatorios" / "complementacao" / snapshot["run_id"]
    report_directory.mkdir(parents=True, exist_ok=True)
    html_path = report_directory / "relatorio.html"
    csv_path = report_directory / "relatorio.csv"
    rows = _report_rows(snapshot["run_id"], events)
    html_content = _render_html(snapshot, events, rows)
    csv_content = _render_csv(rows)
    html_temp: Path | None = None
    csv_temp: Path | None = None
    try:
        html_temp = _stage(html_path, html_content)
        csv_temp = _stage(csv_path, csv_content)
        _replace_pair([(html_path, html_temp), (csv_path, csv_temp)])
    finally:
        for temporary in (html_temp, csv_temp):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
    return {
        "run_id": snapshot["run_id"],
        "revision": snapshot["revision"],
        "event_count": len(events),
        "html_path": str(html_path),
        "csv_path": str(csv_path),
    }
