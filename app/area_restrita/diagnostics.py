from __future__ import annotations

import io
import json
import math
import os
import platform
import re
import threading
import uuid
import zipfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit


_ALLOWED_EVENT_FIELDS = frozenset(
    {
        "component",
        "step",
        "elapsed_ms",
        "result",
        "code",
        "process",
        "interested",
        "tab_id",
        "frame_id",
        "url",
        "route",
        "generation",
        "document_nonce",
        "observation_id",
        "publisher_id",
        "sequence",
        "command_id",
        "command_type",
        "fill_state",
        "fields",
        "field",
        "before",
        "proposed",
        "after",
        "warnings",
        "error",
        "reason",
        "active",
        "heartbeat_age_ms",
        "form_state",
        "current_selection_state",
        "build_id",
        "extension_version",
        "capabilities",
        "publisher_sequence",
    }
)
_SECRET_KEY_PARTS = (
    "authorization",
    "bearer",
    "cookie",
    "password",
    "passwd",
    "senha",
    "token",
    "secret",
    "credential",
    "credencial",
    "apikey",
)
_SECRET_TEXT_PATTERNS = (
    re.compile(
        r"(?i)(\b(?:authorization|set-cookie|cookie|password|passwd|senha|extension[_-]?token|access[_-]?token|refresh[_-]?token|token|secret|credential|credencial|api[_-]?key)\b\s*[:=]\s*)(?:bearer\s+)?([^\s,;]+)"
    ),
    re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)(\b(?:cookie|set-cookie)\s*[:=]\s*)[^\r\n]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b"),
)
_MAX_EVENT_BYTES = 8 * 1024 * 1024
_TRIM_EVENT_BYTES = 6 * 1024 * 1024
_MAX_SESSIONS = 5
_SLOW_MS = 2_000
_MAX_EVENT_LINE_BYTES = 256 * 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="seconds" if value.microsecond == 0 else "microseconds")


def _redact_text(value: str) -> str:
    redacted = value[:4096]
    for pattern in _SECRET_TEXT_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        elif pattern.groups == 1:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _is_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return (
        any(part in normalized for part in _SECRET_KEY_PARTS)
        or normalized in {"auth", "authheader", "authentication", "authenticationheader"}
    )


def _safe_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if not parts.scheme and not parts.netloc:
            return parts.path[:2048]
        hostname = parts.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        if parts.port is not None:
            hostname = f"{hostname}:{parts.port}"
        return urlunsplit((parts.scheme, hostname, parts.path, "", ""))[:2048]
    except (TypeError, ValueError):
        return ""


def _safe_value(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    if key is not None and _is_secret_key(key):
        return None
    if depth > 6:
        return None
    if isinstance(value, str):
        if key in {"url", "route"}:
            return _safe_url(value)
        return _redact_text(value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for index, (nested_key, nested_value) in enumerate(value.items()):
            if index >= 200:
                break
            if not isinstance(nested_key, str) or _is_secret_key(nested_key):
                continue
            nested_safe = _safe_value(nested_value, key=nested_key, depth=depth + 1)
            if nested_safe is not None:
                safe[nested_key[:128]] = nested_safe
        return safe
    if isinstance(value, (list, tuple)):
        return [
            nested
            for item in value[:100]
            if (nested := _safe_value(item, depth=depth + 1)) is not None
        ]
    return None


class DiagnosticRecorder:
    """Bounded local-only timeline, isolated from operational/qualification state."""

    def __init__(
        self,
        data_root: Path,
        *,
        build_id: str,
        extension_version: str,
        utcnow: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._root = Path(data_root) / "diagnostics"
        self._sessions_dir = self._root / "sessions"
        self._settings_path = self._root / "settings.json"
        self._build_id = _redact_text(str(build_id))[:256]
        self._extension_version = _redact_text(str(extension_version))[:128]
        self._utcnow = utcnow
        self._lock = threading.RLock()
        self._paused = False
        self._event_count = 0
        self._last_event: dict[str, Any] | None = None
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._write_settings()
        self._session_id = uuid.uuid4().hex
        self._session_started_at = _timestamp(self._utcnow())
        self._session_path = self._sessions_dir / f"{self._session_id}.jsonl"
        self._session_path.touch(exist_ok=False)
        self._prune_sessions()

    def _write_settings(self) -> None:
        self._atomic_write(
            self._settings_path,
            json.dumps({"diagnostic_enabled": True}, ensure_ascii=False).encode("utf-8"),
        )

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _prune_sessions(self) -> None:
        sessions = sorted(
            self._sessions_dir.glob("*.jsonl"),
            key=lambda item: (item.stat().st_mtime_ns, item.name),
            reverse=True,
        )
        for stale in sessions[_MAX_SESSIONS:]:
            stale.unlink(missing_ok=True)

    def _trim_active_session(self) -> None:
        size = self._session_path.stat().st_size
        if size <= _MAX_EVENT_BYTES:
            return
        data = self._session_path.read_bytes()
        start = max(0, len(data) - _TRIM_EVENT_BYTES)
        boundary = data.find(b"\n", start)
        if boundary >= 0:
            data = data[boundary + 1 :]
        self._atomic_write(self._session_path, data)

    def record(self, event: Mapping[str, Any]) -> bool:
        if not isinstance(event, Mapping):
            return False
        with self._lock:
            if self._paused:
                return False
            safe: dict[str, Any] = {}
            for key, value in event.items():
                if not isinstance(key, str) or key not in _ALLOWED_EVENT_FIELDS:
                    continue
                sanitized = _safe_value(value, key=key)
                if sanitized is not None:
                    safe[key] = sanitized
            elapsed = safe.get("elapsed_ms")
            if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and elapsed >= _SLOW_MS:
                safe["severity"] = "SLOW"
            safe["timestamp"] = _timestamp(self._utcnow())
            safe["session_id"] = self._session_id
            line = (json.dumps(safe, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            if len(line) > _MAX_EVENT_LINE_BYTES:
                return False
            try:
                with self._session_path.open("ab") as stream:
                    stream.write(line)
                self._trim_active_session()
            except OSError:
                return False
            self._event_count += 1
            self._last_event = safe
            return True

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "diagnostic_enabled": True,
                "active": not self._paused,
                "paused": self._paused,
                "session_id": self._session_id,
                "event_count": self._event_count,
                "last_event": dict(self._last_event) if self._last_event is not None else None,
                "retained_sessions": len(tuple(self._sessions_dir.glob("*.jsonl"))),
                "build_id": self._build_id,
                "extension_version": self._extension_version,
            }

    def pause(self) -> dict[str, Any]:
        with self._lock:
            self._paused = True
            return self.status()

    def resume(self) -> dict[str, Any]:
        with self._lock:
            self._paused = False
            return self.status()

    def clear(self) -> dict[str, Any]:
        with self._lock:
            was_paused = self._paused
            for old_session in self._sessions_dir.glob("*.jsonl"):
                old_session.unlink(missing_ok=True)
            self._session_id = uuid.uuid4().hex
            self._session_started_at = _timestamp(self._utcnow())
            self._session_path = self._sessions_dir / f"{self._session_id}.jsonl"
            self._session_path.touch(exist_ok=False)
            self._event_count = 0
            self._last_event = None
            self._paused = was_paused
            self._write_settings()
            return self.status()

    def export_zip(self, *, capabilities: Mapping[str, Any]) -> tuple[str, bytes]:
        with self._lock:
            session_files = sorted(
                self._sessions_dir.glob("*.jsonl"),
                key=lambda item: (item.stat().st_mtime_ns, item.name),
            )
            event_lines: list[str] = []
            events: list[dict[str, Any]] = []
            for session_file in session_files:
                for line in session_file.read_text(encoding="utf-8").splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict):
                        events.append(event)
                        event_lines.append(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            safe_capabilities = _safe_value(capabilities)
            current_session_events = [
                event for event in events if event.get("session_id") == self._session_id
            ]
            environment = {
                "build_id": self._build_id,
                "extension_version": self._extension_version,
                "capabilities": safe_capabilities if isinstance(safe_capabilities, dict) else {},
                "runtime": {
                    "os": platform.system(),
                    "os_release": platform.release(),
                    "architecture": platform.machine(),
                    "python_version": platform.python_version(),
                },
                "exported_at": _timestamp(self._utcnow()),
                "session_id": self._session_id,
            }
            latest = current_session_events[-1] if current_session_events else (events[-1] if events else {})
            summary = self._build_summary(events, environment, latest)
            mesa_events = [event for event in events if event.get("component") in {"mesa", "server", "fill_service"}]
            extension_events = [event for event in events if event.get("component") == "extension"]
            files = {
                "resumo.txt": summary.encode("utf-8"),
                "timeline.jsonl": ("\n".join(event_lines) + ("\n" if event_lines else "")).encode("utf-8"),
                "ambiente.json": json.dumps(environment, ensure_ascii=False, indent=2).encode("utf-8"),
                "mesa.log": self._events_as_log(mesa_events).encode("utf-8"),
                "extensao.log": self._events_as_log(extension_events).encode("utf-8"),
                "ultima-sessao.json": json.dumps(
                    {
                        "session_id": self._session_id,
                        "started_at": self._session_started_at,
                        "events": current_session_events,
                    },
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8"),
            }
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in files.items():
                    archive.writestr(name, content)
            filename = f"diagnostico-atos-tce-{self._utcnow().strftime('%Y%m%d-%H%M%S')}.zip"
            return filename, output.getvalue()

    @staticmethod
    def _events_as_log(events: list[dict[str, Any]]) -> str:
        return "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)

    @staticmethod
    def _build_summary(
        events: list[dict[str, Any]], environment: dict[str, Any], latest: dict[str, Any]
    ) -> str:
        failures = [
            event
            for event in events
            if str(event.get("result", "")).casefold() in {"error", "failed", "failure", "timeout", "refused"}
            or any(
                marker in str(event.get(field, "")).upper()
                for marker in ("TIMEOUT", "NOT_AVAILABLE", "STALE_FORM", "ERROR")
                for field in ("code", "step")
            )
        ]
        slow = [event for event in events if event.get("severity") == "SLOW"]
        lines = [
            "Modo Diagnóstico — Atos-TCE",
            f"Sessão: {environment['session_id']}",
            f"Build ID: {environment['build_id']}",
            f"Versão da extensão: {environment['extension_version']}",
            f"Capabilities: {json.dumps(environment['capabilities'], ensure_ascii=False, sort_keys=True)}",
            f"Eventos: {len(events)}",
            "",
            f"Falhas e recusas: {len(failures)}",
        ]
        lines.extend(DiagnosticRecorder._event_summary(event) for event in failures[:50])
        lines.extend(["", f"Timeouts: {sum('TIMEOUT' in str(event.get('code', '')).upper() or 'TIMEOUT' in str(event.get('step', '')).upper() for event in events)}"])
        lines.append(f"Etapas SLOW: {len(slow)}")
        lines.extend(DiagnosticRecorder._event_summary(event) for event in slow[:50])
        lines.extend(["", "Último estado conhecido:"])
        lines.append(DiagnosticRecorder._event_summary(latest) if latest else "Nenhum evento registrado.")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _event_summary(event: dict[str, Any]) -> str:
        parts = [str(event.get(key, "")) for key in ("timestamp", "component", "step")]
        code = event.get("code") or event.get("result") or ""
        parts.append(str(code))
        if "elapsed_ms" in event:
            parts.append(f"{event['elapsed_ms']} ms")
        if event.get("severity") == "SLOW":
            parts.append("SLOW")
        return " | ".join(part for part in parts if part)
