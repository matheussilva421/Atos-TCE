"""Fail-closed sanitizer for structural browser captures."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import unquote, urlsplit, urlunsplit


MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_COLLECTION_ITEMS = 5000
MAX_DEPTH = 24

CPF_RE = re.compile(r"(?<!\d)(?:\d{3}[.\s-]?){2}\d{3}[.\s-]?\d{2}(?!\d)")
PROCESS_RE = re.compile(r"(?<!\d)\d{3,9}/\d{4}(?!\d)")
TOKEN_RE = re.compile(
    r"(?i)(?:\bbearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"\b(?:access|refresh|auth|session)?_?token\s*[:=]\s*[A-Za-z0-9._~+/=-]{8,}|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"
)
SENSITIVE_PATTERNS = (CPF_RE, PROCESS_RE, TOKEN_RE)
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:#\[\]-]{0,127}$")
VERSION_RE = re.compile(r"^[0-9]+(?:\.[A-Za-z0-9-]+){0,5}$")

DENIED_KEYS = {
    "cookie",
    "cookies",
    "header",
    "headers",
    "authorization",
    "storage",
    "localstorage",
    "sessionstorage",
    "value",
    "values",
    "body",
    "requestbody",
    "responsebody",
    "innerhtml",
    "outerhtml",
    "html",
}
TEXT_KEYS = {
    "text",
    "label",
    "title",
    "description",
    "placeholder",
    "message",
    "innertext",
    "textcontent",
    "aria-label",
    "arialabel",
}
CAPTURE_KEYS = {
    "url",
    "route",
    "readyState",
    "framePath",
    "frameBox",
    "controls",
    "forms",
    "sentinels",
    "childFrameCount",
    "tableRows",
    "controlCount",
    "radioCount",
    "selectCount",
    "frames",
    "pages",
    "metadata",
    "schemaVersion",
}
CONTROL_KEYS = ("id", "name", "tag", "tagName", "type")


def _key(value: object) -> str:
    return str(value).replace("_", "").casefold()


def _sensitive_pattern(value: str):
    return next((pattern for pattern in SENSITIVE_PATTERNS if pattern.search(value)), None)


def _classify_text(value: str) -> str:
    if TOKEN_RE.search(value):
        return "credential-like"
    if CPF_RE.search(value):
        return "personal-identifier"
    if PROCESS_RE.search(value):
        return "process-reference"
    return "free-text"


def _identifier(value: object):
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if _sensitive_pattern(candidate):
        raise ValueError("sensitive pattern found in structural identifier")
    if not SAFE_IDENTIFIER_RE.fullmatch(candidate):
        return None
    return candidate


def _safe_route(value: object):
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        parsed = urlsplit(value.strip())
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("userinfo is not allowed in capture routes")
        path = parsed.path or "/"
        if parsed.scheme and parsed.netloc:
            hostname = parsed.hostname
            if not hostname:
                return None
            host = hostname.casefold()
            if parsed.port is not None:
                host = f"{host}:{parsed.port}"
            sanitized = urlunsplit((parsed.scheme.casefold(), host, path, "", ""))
        else:
            sanitized = urlunsplit(("", "", path, "", ""))
    except ValueError:
        return None
    if _sensitive_pattern(unquote(sanitized)):
        raise ValueError("sensitive pattern found in decoded capture route")
    return sanitized if sanitized else None


def _sanitize_frame_path(value: object):
    if isinstance(value, str):
        return _identifier(value)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, list):
        if len(value) > 64:
            raise ValueError("framePath has too many entries")
        result = [_sanitize_frame_path(item) for item in value]
        return [item for item in result if item is not None]
    if isinstance(value, dict):
        result = {}
        for name in ("tag", "tagName", "id", "name", "index"):
            if name not in value:
                continue
            item = value[name]
            if name == "index" and isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                result[name] = item
            else:
                safe = _identifier(item)
                if safe is not None:
                    result[name] = safe
        return result or None
    return None


def _sanitize_control(value: object):
    if not isinstance(value, dict):
        return None
    result = {}
    tag = value.get("tag", value.get("tagName"))
    safe_tag = _identifier(tag.casefold() if isinstance(tag, str) else tag)
    if safe_tag is not None:
        result["tag"] = safe_tag
    for name in ("id", "name", "type"):
        safe = _identifier(value.get(name))
        if safe is not None:
            result[name] = safe
    for name in ("disabled", "readOnly"):
        item = value.get(name)
        if isinstance(item, bool):
            result[name] = item
    option_count = value.get("optionCount", value.get("optionsCount"))
    if isinstance(option_count, int) and not isinstance(option_count, bool) and 0 <= option_count <= 10000:
        result["optionCount"] = option_count
    return result or None


def _sanitize_sentinel(value: object):
    if isinstance(value, str):
        return _identifier(value)
    if isinstance(value, dict):
        result = {}
        for name in ("id", "name", "tag", "type"):
            safe = _identifier(value.get(name))
            if safe is not None:
                result[name] = safe
        return result or None
    return None


def _sanitize_frame_box(value: object):
    if not isinstance(value, dict):
        return None
    result = {}
    for name in ("id", "name"):
        safe = _identifier(value.get(name))
        if safe is not None:
            result[name] = safe
    hidden = value.get("hidden")
    if isinstance(hidden, bool):
        result["hidden"] = hidden
    display = value.get("display")
    if isinstance(display, str) and display.casefold() in {
        "none",
        "block",
        "inline",
        "inline-block",
        "table",
        "table-row",
        "table-cell",
        "flex",
        "grid",
    }:
        result["display"] = display.casefold()
    visibility = value.get("visibility")
    if isinstance(visibility, str) and visibility.casefold() in {"visible", "hidden", "collapse"}:
        result["visibility"] = visibility.casefold()
    for name in ("width", "height"):
        item = value.get(name)
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 10000:
            result[name] = item
    return result or None


def _sanitize_form(value: object):
    if not isinstance(value, dict):
        return None
    result = {}
    for name in ("id", "name"):
        safe = _identifier(value.get(name))
        if safe is not None:
            result[name] = safe
    method = value.get("method")
    if isinstance(method, str) and method.strip().upper() in {"GET", "POST", "DIALOG"}:
        result["method"] = method.strip().upper()
    count = value.get("controlCount")
    if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 10000:
        result["controlCount"] = count
    return result or None


def _sanitize_metadata(value: object):
    if not isinstance(value, dict):
        return None
    result = {}
    schema_version = value.get("schemaVersion")
    if isinstance(schema_version, int) and not isinstance(schema_version, bool) and 1 <= schema_version <= 99:
        result["schemaVersion"] = schema_version
    for name in ("toolVersion", "browserVersion"):
        candidate = value.get(name)
        if isinstance(candidate, str) and VERSION_RE.fullmatch(candidate):
            result[name] = candidate
    return result or None


def _sanitize_capture(value: object, depth: int):
    if depth > MAX_DEPTH:
        raise ValueError("capture nesting is too deep")
    if not isinstance(value, dict):
        raise ValueError("capture entries must be JSON objects")
    result = {}
    for raw_name, item in value.items():
        normalized = _key(raw_name)
        if normalized in DENIED_KEYS:
            continue
        if normalized in TEXT_KEYS:
            if isinstance(item, str) and item.strip():
                result[f"{raw_name}Class"] = _classify_text(item)
            continue
        if raw_name not in CAPTURE_KEYS:
            continue
        if normalized in {"url", "route"}:
            safe_route = _safe_route(item)
            if safe_route is not None:
                result["url" if normalized == "url" else "route"] = safe_route
        elif normalized == "readystate":
            if isinstance(item, str) and item.casefold() in {"loading", "interactive", "complete"}:
                result["readyState"] = item.casefold()
        elif normalized == "framepath":
            frame_path = _sanitize_frame_path(item)
            if frame_path is not None:
                result["framePath"] = frame_path
        elif normalized == "framebox":
            frame_box = _sanitize_frame_box(item)
            if frame_box:
                result["frameBox"] = frame_box
        elif normalized == "controls" and isinstance(item, list):
            if len(item) > MAX_COLLECTION_ITEMS:
                raise ValueError("controls collection is too large")
            controls = [_sanitize_control(control) for control in item]
            result["controls"] = [control for control in controls if control is not None]
        elif normalized == "forms" and isinstance(item, list):
            if len(item) > 256:
                raise ValueError("forms collection is too large")
            forms = [_sanitize_form(form) for form in item]
            result["forms"] = [form for form in forms if form is not None]
        elif normalized == "sentinels" and isinstance(item, list):
            if len(item) > MAX_COLLECTION_ITEMS:
                raise ValueError("sentinels collection is too large")
            sentinels = [_sanitize_sentinel(sentinel) for sentinel in item]
            result["sentinels"] = [sentinel for sentinel in sentinels if sentinel is not None]
        elif normalized == "childframecount":
            if isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 10000:
                result["childFrameCount"] = item
        elif normalized in {"tablerows", "controlcount", "radiocount", "selectcount"}:
            if isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 10000:
                canonical_name = {
                    "tablerows": "tableRows",
                    "controlcount": "controlCount",
                    "radiocount": "radioCount",
                    "selectcount": "selectCount",
                }[normalized]
                result[canonical_name] = item
        elif normalized in {"frames", "pages"} and isinstance(item, list):
            if len(item) > MAX_COLLECTION_ITEMS:
                raise ValueError(f"{normalized} collection is too large")
            children = [_sanitize_capture(child, depth + 1) for child in item]
            result[normalized] = children
        elif normalized == "metadata":
            metadata = _sanitize_metadata(item)
            if metadata:
                result["metadata"] = metadata
        elif normalized == "schemaversion":
            if isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= 99:
                result["schemaVersion"] = item
    return result


def _validate_clean_output(value: object):
    if isinstance(value, str):
        if _sensitive_pattern(value):
            raise ValueError("sanitized output contains a sensitive identifier or token pattern")
    elif isinstance(value, list):
        for item in value:
            _validate_clean_output(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_clean_output(key)
            _validate_clean_output(item)


def sanitize_capture(raw: object):
    """Return only allowlisted structure; reject any sensitive pattern left over."""
    if not isinstance(raw, dict):
        raise ValueError("capture root must be a JSON object")
    clean = _sanitize_capture(raw, depth=0)
    _validate_clean_output(clean)
    return clean


def _write_output(path: Path, content: str, *, force: bool = False):
    if path.is_symlink():
        raise ValueError("output path must not be a symbolic link")
    path = path.resolve()
    if not path.parent.is_dir():
        raise ValueError("output directory does not exist")
    if path.exists() and not force:
        raise ValueError("output already exists; pass --force to replace it")
    if path.exists() and not path.is_file():
        raise ValueError("output path must be a file")
    fd, temporary = tempfile.mkstemp(prefix=".sanitize-capture-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="raw capture JSON (read only)")
    parser.add_argument("output", nargs="?", type=Path, help="destination for sanitized JSON; defaults to stdout")
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError("input capture exceeds the size limit")
        if args.output and args.output.resolve() == args.input.resolve():
            raise ValueError("input and output paths must be different")
        raw = json.loads(args.input.read_text(encoding="utf-8-sig"))
        clean = sanitize_capture(raw)
        encoded = json.dumps(clean, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_output(args.output, encoded, force=args.force)
        else:
            sys.stdout.write(encoded)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"sanitize-capture: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
