"""Resolve a next target from one exact, ordered Área Restrita scan."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.identity import normalize_interested
from ..core.store import Store


class NavigationError(ValueError):
    """Fail-closed refusal to resolve a safe next-process target."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _identity_of(process: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "processKey": str(process.get("process_key") or ""),
        "interestedNormalized": str(process.get("interested_normalized") or ""),
        "portalActId": process.get("portal_act_id"),
    }


def _same_identity(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_key = str(left.get("process_key") or left.get("processKey") or "").strip()
    right_key = str(right.get("process_key") or right.get("processKey") or "").strip()
    left_interested = normalize_interested(
        left.get("interested_normalized") or left.get("interestedNormalized") or ""
    )
    right_interested = normalize_interested(
        right.get("interested_normalized") or right.get("interestedNormalized") or ""
    )
    return bool(left_key and left_interested and left_key == right_key and left_interested == right_interested)


class NavigationService:
    """Select the first later process that is still ready to complement.

    The Mesa owns queue selection. This service never sorts process keys,
    wraps to the start, or substitutes a neighboring row for an exact identity.
    """

    def __init__(self, store: Store):
        self._store = store

    def next_target(
        self,
        *,
        process_id: int | None = None,
        identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return the next exact target after ``process_id``/``identity``.

        ``None`` is reserved for a valid end-of-queue. Invalid, stale, or
        ambiguous state raises :class:`NavigationError` with a non-sensitive
        machine-readable ``code``.
        """

        current = self._resolve_current(process_id=process_id, identity=identity)
        scan_id = current.get("last_area_scan_id")
        if scan_id is None:
            raise NavigationError("scan_unavailable")
        try:
            scan_id = int(scan_id)
        except (TypeError, ValueError):
            raise NavigationError("scan_unavailable") from None

        scan = self._store.latest_area_scan()
        if scan is None:
            raise NavigationError("scan_unavailable")
        if int(scan["id"]) != scan_id:
            raise NavigationError("stale_scan")

        items = scan.get("items")
        if not isinstance(items, list) or int(scan.get("total") or 0) != len(items):
            raise NavigationError("incomplete_scan")
        # Preserve the scan context byte-for-byte for the extension to verify.
        source_scope = str(scan.get("source_scope") or "")
        marker_label = str(scan.get("marker_label") or "")
        marker_value = str(scan.get("marker_value") or "")
        if not source_scope.strip() or not marker_label.strip() or not marker_value.strip():
            raise NavigationError("missing_scan_context")
        if current.get("source_scope") != source_scope or current.get("marker") != marker_label:
            raise NavigationError("scan_context_mismatch")

        current_positions = [
            index
            for index, item in enumerate(items)
            if _same_identity(item, current)
        ]
        if len(current_positions) != 1:
            raise NavigationError(
                "current_process_not_in_scan" if not current_positions else "ambiguous_current_process"
            )
        current_index = current_positions[0]
        current_item = items[current_index]
        if int(current_item.get("process_id") or 0) != int(current["id"]):
            raise NavigationError("current_process_mismatch")

        for item in items[current_index + 1 :]:
            target_id = item.get("process_id")
            try:
                target_id = int(target_id)
            except (TypeError, ValueError):
                raise NavigationError("invalid_scan_item") from None
            target = self._store.get_process(target_id)
            if target is None or not _same_identity(item, target):
                raise NavigationError("stale_scan_item")
            if int(target.get("last_area_scan_id") or 0) != scan_id:
                raise NavigationError("stale_scan_item")
            if target.get("source_scope") != source_scope or target.get("marker") != marker_label:
                raise NavigationError("scan_context_mismatch")
            if (
                item.get("classification") != target.get("area_classification")
                or bool(item.get("needs_complement")) != bool(target.get("needs_complement"))
            ):
                raise NavigationError("stale_scan_item")

            if (
                target.get("status") == "PRONTO"
                and bool(target.get("needs_complement"))
                and target.get("area_classification") == "PRECISA_COMPLEMENTAR"
            ):
                return {
                    "current_identity": _identity_of(current),
                    "target_identity": _identity_of(target),
                    "scan_id": scan_id,
                    "source_scope": source_scope,
                    "marker": {"label": marker_label, "value": marker_value},
                }

        return None

    def _resolve_current(
        self,
        *,
        process_id: int | None,
        identity: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        by_id: dict[str, Any] | None = None
        if process_id is not None:
            if isinstance(process_id, bool):
                raise NavigationError("invalid_process_id")
            try:
                by_id = self._store.get_process(int(process_id))
            except (TypeError, ValueError):
                raise NavigationError("invalid_process_id") from None
            if by_id is None:
                raise NavigationError("current_process_not_found")

        by_identity: dict[str, Any] | None = None
        if identity is not None:
            if not isinstance(identity, Mapping):
                raise NavigationError("invalid_identity")
            process_key = str(identity.get("processKey") or identity.get("process_key") or "").strip()
            interested = normalize_interested(
                identity.get("interestedNormalized") or identity.get("interested_normalized") or ""
            )
            portal_act_id = identity.get("portalActId") or identity.get("portal_act_id")
            if not process_key:
                raise NavigationError("invalid_identity")
            candidates = [
                process
                for process in self._store.list_processes()
                if str(process.get("process_key") or "") == process_key
                and (not interested or normalize_interested(process.get("interested_normalized")) == interested)
                and (portal_act_id is None or str(process.get("portal_act_id") or "") == str(portal_act_id))
            ]
            if not candidates:
                raise NavigationError("current_process_not_found")
            if len(candidates) != 1:
                raise NavigationError("ambiguous_identity")
            by_identity = candidates[0]

        if by_id is None and by_identity is None:
            raise NavigationError("current_process_required")
        if by_id is not None and by_identity is not None and int(by_id["id"]) != int(by_identity["id"]):
            raise NavigationError("current_identity_mismatch")
        current_id = int((by_id or by_identity)["id"])
        current = self._store.get_process(current_id)
        if current is None:
            raise NavigationError("current_process_not_found")
        return current


__all__ = ["NavigationError", "NavigationService"]
