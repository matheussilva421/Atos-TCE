"""Canonical identity normalization shared by every Mesa adapter.

The natural key of a logical process is ``(process_key, interested_normalized)``.
The portal scanner (JavaScript), the legacy importer and the analysis pipeline
must all produce byte-identical ``interested_normalized`` values, otherwise the
same act would appear twice. This module is the single Python owner of that
rule; ``extension/lib/portal-matcher.js`` and ``extension/lib/protocol.js``
mirror it for the browser side.

The rule is ported verbatim from the proven legacy implementation in
``analysis_pipeline._normalise_interested`` and
``extensao-complementar-ato/lib/automation-schema.js``:

    NFKD -> drop combining marks -> casefold -> collapse whitespace -> trim
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def strip_marks(value: str) -> str:
    """Return ``value`` decomposed and without any combining/mark character."""

    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_interested(value: object) -> str:
    """Normalize an interested-person name into its canonical comparison form."""

    text = strip_marks(str(value or ""))
    return _WHITESPACE_RE.sub(" ", text.casefold()).strip()


def normalize_text(value: object) -> str:
    """Normalize free text for tolerant comparison (accent and case insensitive)."""

    return normalize_interested(value)


def is_normalized_interested(value: object) -> bool:
    """True when ``value`` is already in canonical form (idempotency guard)."""

    if not isinstance(value, str) or not value:
        return False
    return normalize_interested(value) == value
