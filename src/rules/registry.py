"""Every rule in the system, in BRD order.

Section headings and the order they print in are NOT here: they live in
src/templates/post-check-template.md, which also declares - with its
`<!-- rules: ... -->` markers - which criteria print under which section.
verify_template asserts every rule below appears there exactly once.

The import-time check below is why a mistyped fact path cannot become a silent
unchecked row: it raises when this module is first imported, which happens
before any run.
"""

from __future__ import annotations

from src.rules import criteria, dossier, ews, fraud, identity, operation
from src.rules.engine import Rule, validate_needs


RULES: tuple[Rule, ...] = (
    *identity.RULES,    # BRD 2.1   - V01..V07
    *fraud.RULES,       # BRD 2.2   - F01..F02
    *dossier.RULES,     # BRD 2.3   - P01..P07
    *criteria.RULES,    # BRD 2.3   - C01..C03
    *operation.RULES,   # BRD 2.3   - O01..O04, plus O05..O08 outside the BRD
    *ews.RULES,         # BRD 2.4   - E01..E06
)


validate_needs(RULES)
