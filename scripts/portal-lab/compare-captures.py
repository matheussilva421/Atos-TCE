"""Compare two sanitized structural Portal Lab captures."""

from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys


MAX_INPUT_BYTES = 5 * 1024 * 1024
SANITIZER_PATH = Path(__file__).with_name("sanitize-capture.py")


def _load_sanitizer():
    spec = importlib.util.spec_from_file_location("portal_lab_sanitizer", SANITIZER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("sanitizer is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.sanitize_capture


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _merge_frame(frame, defaults):
    merged = dict(defaults)
    merged.update(frame)
    return merged


def _extract_frames(capture):
    if isinstance(capture, list):
        pages = capture
        defaults = {}
    elif isinstance(capture, dict):
        defaults = {key: capture[key] for key in ("route", "readyState") if key in capture}
        if isinstance(capture.get("pages"), list):
            pages = capture["pages"]
        elif isinstance(capture.get("frames"), list):
            pages = capture["frames"]
        else:
            pages = [capture]
    else:
        raise ValueError("capture root must be an object or array")

    frames = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page = _merge_frame(page, defaults)
        nested = page.get("frames")
        if isinstance(nested, list):
            page_defaults = {key: page[key] for key in ("route", "readyState") if key in page}
            frames.extend(_merge_frame(frame, page_defaults) for frame in nested if isinstance(frame, dict))
        elif "framePath" in page or "controls" in page or "route" in page:
            frames.append(page)
    return frames


def _path(frame):
    return frame.get("framePath", ["top"])


def _path_sort(value):
    if isinstance(value, list):
        return tuple((type(item).__name__, str(item)) for item in value)
    if isinstance(value, str):
        return (("str", value),)
    return (("json", _canonical(value)),)


def _frame_map(capture):
    result = {}
    for frame in _extract_frames(capture):
        identity = _canonical(_path(frame))
        if identity in result:
            raise ValueError("capture contains duplicate framePath values")
        result[identity] = frame
    return result


def _control_identity(control, index):
    identity = [control.get(key) for key in ("tag", "id", "name", "type")]
    if not identity[1] and not identity[2]:
        identity.append(index)
    return _canonical(identity)


def _counter_delta(before, after, label, frame_path):
    left = Counter(_canonical(item) for item in before)
    right = Counter(_canonical(item) for item in after)
    before_by_key = {_canonical(item): item for item in before}
    after_by_key = {_canonical(item): item for item in after}
    removed = []
    added = []
    for key in sorted(left.keys() | right.keys()):
        removed.extend({"framePath": frame_path, label: before_by_key[key]} for _ in range(max(0, left[key] - right[key])))
        added.extend({"framePath": frame_path, label: after_by_key[key]} for _ in range(max(0, right[key] - left[key])))
    return added, removed


def compare_captures(before, after):
    before_frames = _frame_map(before)
    after_frames = _frame_map(after)
    before_keys = set(before_frames)
    after_keys = set(after_frames)

    result = {
        "framesAdded": [
            {"framePath": _path(after_frames[key])}
            for key in sorted(after_keys - before_keys, key=lambda item: _path_sort(_path(after_frames[item])))
        ],
        "framesRemoved": [
            {"framePath": _path(before_frames[key])}
            for key in sorted(before_keys - after_keys, key=lambda item: _path_sort(_path(before_frames[item])))
        ],
        "routesChanged": [],
        "sentinelsAdded": [],
        "sentinelsRemoved": [],
        "controlsAdded": [],
        "controlsRemoved": [],
        "controlsChanged": [],
        "readyStateChanges": [],
    }

    for key in sorted(after_keys - before_keys):
        frame = after_frames[key]
        frame_path = _path(frame)
        result["sentinelsAdded"].extend(
            {"framePath": frame_path, "sentinel": sentinel}
            for sentinel in sorted(frame.get("sentinels", []), key=_canonical)
        )
        result["controlsAdded"].extend(
            {"framePath": frame_path, "control": control}
            for control in sorted(frame.get("controls", []), key=_canonical)
        )
    for key in sorted(before_keys - after_keys):
        frame = before_frames[key]
        frame_path = _path(frame)
        result["sentinelsRemoved"].extend(
            {"framePath": frame_path, "sentinel": sentinel}
            for sentinel in sorted(frame.get("sentinels", []), key=_canonical)
        )
        result["controlsRemoved"].extend(
            {"framePath": frame_path, "control": control}
            for control in sorted(frame.get("controls", []), key=_canonical)
        )

    for key in sorted(before_keys & after_keys):
        old = before_frames[key]
        new = after_frames[key]
        frame_path = _path(new)
        if old.get("route") != new.get("route"):
            result["routesChanged"].append(
                {"framePath": frame_path, "before": old.get("route"), "after": new.get("route")}
            )
        if old.get("readyState") != new.get("readyState"):
            result["readyStateChanges"].append(
                {"framePath": frame_path, "before": old.get("readyState"), "after": new.get("readyState")}
            )

        sentinels_added, sentinels_removed = _counter_delta(
            old.get("sentinels", []), new.get("sentinels", []), "sentinel", frame_path
        )
        result["sentinelsAdded"].extend(sentinels_added)
        result["sentinelsRemoved"].extend(sentinels_removed)

        old_controls = old.get("controls", [])
        new_controls = new.get("controls", [])
        old_by_identity = {_control_identity(item, index): item for index, item in enumerate(old_controls)}
        new_by_identity = {_control_identity(item, index): item for index, item in enumerate(new_controls)}
        for identity in sorted(old_by_identity.keys() - new_by_identity.keys()):
            result["controlsRemoved"].append({"framePath": frame_path, "control": old_by_identity[identity]})
        for identity in sorted(new_by_identity.keys() - old_by_identity.keys()):
            result["controlsAdded"].append({"framePath": frame_path, "control": new_by_identity[identity]})
        for identity in sorted(old_by_identity.keys() & new_by_identity.keys()):
            if old_by_identity[identity] != new_by_identity[identity]:
                result["controlsChanged"].append(
                    {
                        "framePath": frame_path,
                        "before": old_by_identity[identity],
                        "after": new_by_identity[identity],
                    }
                )

    for entries in result.values():
        entries.sort(
            key=lambda entry: (
                _path_sort(entry.get("framePath")),
                _canonical({key: value for key, value in entry.items() if key != "framePath"}),
            )
        )
    return result


def _read_capture(path: Path, sanitize):
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("capture exceeds the size limit")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    return sanitize(raw)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2:
        print("usage: compare-captures.py before.json after.json", file=sys.stderr)
        return 2
    try:
        sanitize = _load_sanitizer()
        before = _read_capture(Path(argv[0]), sanitize)
        after = _read_capture(Path(argv[1]), sanitize)
        result = compare_captures(before, after)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        print(f"compare-captures: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
