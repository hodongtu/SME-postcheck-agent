"""Shared types for the post-check workflow."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypedDict

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

    document_type: str = ""           # a DocumentType.id, or "" when unrecognised
    document_group: str = ""
    document_type_note: str = ""

    financial_statement: dict[str, Any] | None = None
    financial_statement_error: str = ""
    proposal: dict[str, Any] | None = None
    proposal_error: str = ""
    sitevisit: dict[str, Any] | None = None
    sitevisit_photos: dict[str, Any] | None = None
    sitevisit_photos_error: str = ""
    sitevisit_error: str = ""

    @property
    def extension(self) -> str:
        """Lower-cased file extension, including the dot. Drives rule P03."""

        return Path(self.filename).suffix.lower()


class PostcheckGraphState(TypedDict, total=False):
    """State passed between LangGraph workflow nodes.

    Config and settings are NOT here: they are held on the supervisor. Only what
    one step produces for a later one travels in the state.
    """

    case_dir: str
    tax_code: str
    approval_date: str
    postcheck_date: str
    commentary_enabled: bool

    documents: list["PostcheckDocument"]
    extraction_calls: dict[str, int]
    facts: Any
    findings: list[Any]
    commentary: dict[str, str]
    report_markdown: str
    counts: dict[str, int]
    steps: list[str]


def to_dict_list(items: list[Any]) -> list[dict[str, Any]]:
    """Convert dataclasses to JSON-friendly dictionaries."""

    return [
        asdict(item) if hasattr(item, "__dataclass_fields__") else item
        for item in items
    ]
