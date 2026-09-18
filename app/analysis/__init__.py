"""Analysis layer: document classification, field extraction and evidence.

The proven incremental pipeline stays the execution engine behind an adapter
(``legacy_adapter``); this package owns the *normalized* shape the Mesa stores
and the rules that decide PRONTO, REVISAR or ERRO.
"""

#: Six fields decide whether an act can be filled at all.
MANDATORY_FIELDS: tuple[str, ...] = (
    "modalidade",
    "fundamento_legal",
    "data_publicacao_doe",
    "cargo",
    "matricula",
    "data_nascimento",
)

#: Optional on purpose: the portal accepts an empty value here.
OPTIONAL_FIELDS: tuple[str, ...] = ("genero",)

KNOWN_FIELDS: tuple[str, ...] = MANDATORY_FIELDS + OPTIONAL_FIELDS

__all__ = ["MANDATORY_FIELDS", "OPTIONAL_FIELDS", "KNOWN_FIELDS"]
