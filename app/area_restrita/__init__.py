"""Área Restrita adapter layer.

This package owns the Python-side vocabulary of the portal: the roles a
snapshot may declare and the classification set the scanner produces. The
extension mirrors the same names; ``tests/test_extension_parity.py`` keeps both
sides honest.
"""

#: Roles a sanitized snapshot may declare. Anything else is refused, so a
#: malformed payload can never be persisted as a scan.
PORTAL_ROLES = frozenset({"list", "interested", "form", "buttons", "unknown"})

#: Classification vocabulary produced by extension/lib/area-snapshot.js.
AREA_CLASSIFICATIONS = (
    "PRECISA_COMPLEMENTAR",
    "ATO_COMPLEMENTADO",
    "NAO_ENCONTRADO_AREA_RESTRITA",
    "AMBIGUO",
    "BLOQUEADO",
)

__all__ = ["PORTAL_ROLES", "AREA_CLASSIFICATIONS"]
