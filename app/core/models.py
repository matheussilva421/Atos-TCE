"""Frozen data contracts shared by the Mesa domain layer.

These dataclasses are the only shapes the store accepts. Adapters translate
portal, collector and analysis payloads into them, so nothing downstream has to
guess whether a value came from a browser, a PDF or a job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Normal workflow states, in the order the design spec describes them.
WORKFLOW_STATES: tuple[str, ...] = (
    "PENDENTE",
    "IDENTIFICADO",
    "BAIXANDO",
    "BAIXADO",
    "ANALISANDO",
    "REVISAR",
    "PRONTO",
    "PREENCHIDO",
    "CONCLUÍDO",
)

# Exceptional workflow states. These never advance to PRONTO on their own.
EXCEPTIONAL_STATES: tuple[str, ...] = ("ERRO", "BLOQUEADO", "DIVERGENCIA")

ALL_STATES: frozenset[str] = frozenset(WORKFLOW_STATES + EXCEPTIONAL_STATES)

#: What the Área Restrita can report about one process/interested pair.
AREA_CLASSIFICATIONS: tuple[str, ...] = (
    "PRECISA_COMPLEMENTAR",
    "ATO_COMPLEMENTADO",
    "NAO_ENCONTRADO_AREA_RESTRITA",
    "AMBIGUO",
    "BLOQUEADO",
)

#: Fail-closed target for each portal observation. ``AMBIGUO``,
#: ``NAO_ENCONTRADO_AREA_RESTRITA`` and an unknown classification never reach
#: PRONTO on their own; ``BLOQUEADO`` stays visible as an exceptional state.
AREA_CLASSIFICATION_TARGET: dict[str, str] = {
    "PRECISA_COMPLEMENTAR": "PENDENTE",
    "ATO_COMPLEMENTADO": "CONCLUÍDO",
    "NAO_ENCONTRADO_AREA_RESTRITA": "PENDENTE",
    "AMBIGUO": "PENDENTE",
    "BLOQUEADO": "BLOQUEADO",
}

#: Workflow event recorded when the portal moves a process to each state.
AREA_CLASSIFICATION_EVENT: dict[str, str] = {
    "PRECISA_COMPLEMENTAR": "portal_pending",
    "ATO_COMPLEMENTADO": "portal_completed",
    "NAO_ENCONTRADO_AREA_RESTRITA": "portal_not_found",
    "AMBIGUO": "portal_ambiguous",
    "BLOQUEADO": "portal_blocked",
}


def status_rank(status: str) -> int:
    """Order workflow states, so a scan never regresses finished work.

    Exceptional states (ERRO, BLOQUEADO, DIVERGENCIA) rank below PENDENTE: a new
    portal observation is allowed to clear them.
    """

    try:
        return WORKFLOW_STATES.index(status)
    except ValueError:
        return -1

# Documents are HOT while their bytes are local, ARCHIVED when only an external
# verified copy remains, MISSING when no verified copy is reachable.
STORAGE_STATES: tuple[str, ...] = ("HOT", "ARCHIVED", "MISSING")


@dataclass(frozen=True, slots=True)
class ProcessRecord:
    """One logical process owned by one interested person."""

    process_key: str
    interested: str
    interested_normalized: str
    source_scope: str | None = None
    marker: str | None = None
    status: str = "PENDENTE"

    def __post_init__(self) -> None:
        if not self.process_key.strip():
            raise ValueError("process_key is required")
        if not self.interested.strip():
            raise ValueError("interested is required")
        if not self.interested_normalized.strip():
            raise ValueError("interested_normalized is required")


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """One PDF (or document) belonging to a process."""

    source_id: str
    title: str
    relative_path: str
    sha256: str
    page_count: int = 0
    event: str | None = None
    classification: str | None = None
    storage_state: str = "HOT"

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.sha256.strip():
            raise ValueError("sha256 is required")
        if self.page_count < 0:
            raise ValueError("page_count cannot be negative")


@dataclass(frozen=True, slots=True)
class FieldRecord:
    """One extracted form field plus the evidence that supports it."""

    field_name: str
    value: str | None = None
    status: str = "pending"
    confidence: float | None = None
    document_id: int | None = None
    page: int | None = None
    evidence: dict[str, Any] | None = field(default=None)

    def __post_init__(self) -> None:
        if not self.field_name.strip():
            raise ValueError("field_name is required")
