"""Shared types for the post-check workflow."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# The document matrix is copied verbatim from SME_creditmemo, and its `agents:`
# keys are validated against this set on load. Post-check does not route to
# specialist agents - it borrows the matrix for keyword-based document
# identification (BRD 2.3.a: map each checklist item from the file name) and
# for the per-type extraction flags. Keeping the names identical is what lets
# document_matrix.py stay unmodified.
SPECIALIST_DOCUMENT_AGENTS = frozenset({
    "FINANCIAL_ANALYSIS_AGENT",
    "BUSINESS_ACTIVITY_AGENT",
    "CREDIT_RELATIONSHIP_AGENT",
    "CREDIT_PROPOSAL_AGENT",
})


@dataclass
class PostcheckDocument:
    """One file from the dossier: its text, its identified type, its extractions.

    The four extraction slots are named after the SME_creditmemo passes that
    fill them, so that a reader can go straight from a slot to the module that
    produced it.
    """

    path: str
    filename: str
    content: str = ""
    file_hash: str = ""
    declared_group: str = ""          # the upload box the file sat in
    extraction_status: str = "success"
    extraction_error: str = ""

    # Identification (src/agents/documents/document_classification.py)
    document_type: str = ""           # a DocumentType.id, or "" when unrecognised
    document_group: str = ""
    document_type_note: str = ""

    # Extraction passes (src/passes.py)
    financial_statement: dict[str, Any] | None = None
    financial_statement_error: str = ""
    proposal: dict[str, Any] | None = None
    proposal_error: str = ""
    sitevisit: dict[str, Any] | None = None
    sitevisit_error: str = ""
    cic_s10a: dict[str, Any] | None = None
    cic_s10a_error: str = ""
    cic_r20: dict[str, Any] | None = None
    cic_r20_error: str = ""

    @property
    def extension(self) -> str:
        """Lower-cased file extension, including the dot. Drives rule P03."""

        return Path(self.filename).suffix.lower()


def to_dict_list(items: list[Any]) -> list[dict[str, Any]]:
    """Convert dataclasses to JSON-friendly dictionaries."""

    return [
        asdict(item) if hasattr(item, "__dataclass_fields__") else item
        for item in items
    ]
