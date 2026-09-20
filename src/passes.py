"""The extraction passes, declared once each.

This module is the WIRING, not the extraction. The prompts and the extract
functions live in src/agents/extraction/, copied verbatim from SME_creditmemo.
Here we only say which pass runs on which document type, where its LLM comes
from on Config, and which PostcheckDocument slot receives the result.

Those modules were tuned over many real runs - monetary-unit handling, period-label normalisation,
reading a tax-filing XML without an LLM, the way CIC prints numbers - and a
comparison rule is only as right as the figure it is given, so none of them is
rewritten here.

Same shape as SME_creditmemo's EXTRACTION_PASSES (supervisor.py:93), minus the
fields post-check does not use. There is deliberately no `batch` field: one
document, one call.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from src.agents.documents.document_matrix import (
    is_financial_statement_type,
    is_sitevisit_photo_type,
    is_proposal_type,
    is_sitevisit_type,
)
from src.agents.extraction.financial_statement_extraction import (
    build_financial_statement_extraction_chain,
    extract_financial_statement_data,
)
from src.agents.extraction.proposal_extraction import (
    build_proposal_extraction_chain,
    extract_proposal_structured_data,
)
from src.agents.extraction.sitevisit_photo_extraction import (
    build_sitevisit_photo_extraction_chain,
    extract_sitevisit_photo_data,
    photo_vocabulary,
)
from src.agents.extraction.sitevisit_extraction import (
    build_sitevisit_extraction_chain,
    extract_sitevisit_structured_data,
)
from src.types import PostcheckDocument


def _always_spends(document: PostcheckDocument) -> bool:
    return True


def _spends_unless_xml(document: PostcheckDocument) -> bool:
    """A tax-filing XML is parsed deterministically, so it costs nothing.

    extract_financial_statement_data tries parse_tax_xml before it touches the
    chain. The runner still has to know, because the budget is about money
    rather than about correctness - and because a pass that cannot spend must
    run even when no LLM is configured at all.
    """

    return document.extension != ".xml"


@dataclass(frozen=True)
class ExtractionPass:
    """One structured-extraction pass, declared once."""

    label: str
    applies_to: Callable[[str], bool]     # document type id -> does this pass run
    result_attr: str
    error_attr: str
    llm_attr: str
    build_chain: Callable[[Any], Any]
    extract: Callable[..., tuple[dict[str, Any] | None, str]]
    # Whether running this pass on this document costs an LLM call.
    spends_llm_call: Callable[[PostcheckDocument], bool] = _always_spends
    # This pass reads the FILE, not the text extracted from it. Image documents
    # have extraction_status "unsupported" and empty content, so the runner skips
    # them by default - a vision pass has to opt back in.
    reads_file: bool = False


EXTRACTION_PASSES: tuple[ExtractionPass, ...] = (
    ExtractionPass(
        label="FINANCIAL_STATEMENT",
        applies_to=is_financial_statement_type,
        result_attr="financial_statement",
        error_attr="financial_statement_error",
        llm_attr="financial_statement_llm",
        build_chain=build_financial_statement_extraction_chain,
        extract=extract_financial_statement_data,
        spends_llm_call=_spends_unless_xml,
    ),
    ExtractionPass(
        label="PROPOSAL",
        applies_to=is_proposal_type,
        result_attr="proposal",
        error_attr="proposal_error",
        llm_attr="proposal_llm",
        build_chain=build_proposal_extraction_chain,
        extract=extract_proposal_structured_data,
    ),
    ExtractionPass(
        label="SITEVISIT_PHOTO",
        applies_to=is_sitevisit_photo_type,
        result_attr="sitevisit_photos",
        error_attr="sitevisit_photos_error",
        llm_attr="sitevisit_photo_llm",
        build_chain=build_sitevisit_photo_extraction_chain,
        extract=extract_sitevisit_photo_data,
        reads_file=True,
    ),
    ExtractionPass(
        label="SITEVISIT",
        applies_to=is_sitevisit_type,
        result_attr="sitevisit",
        error_attr="sitevisit_error",
        llm_attr="sitevisit_llm",
        build_chain=build_sitevisit_extraction_chain,
        extract=extract_sitevisit_structured_data,
    ),
)


def _validate() -> None:
    """Fail on a misdeclared pass at import time, not on the run that needs it."""

    document_fields = set(PostcheckDocument.__dataclass_fields__)
    for extraction_pass in EXTRACTION_PASSES:
        absent = {extraction_pass.result_attr, extraction_pass.error_attr} - document_fields
        if absent:
            raise TypeError(
                f"pass {extraction_pass.label!r}: PostcheckDocument has no "
                f"{sorted(absent)}"
            )
        try:
            extras = ({"vocabulary": [], "max_images": 1}
                      if extraction_pass.reads_file else {})
            inspect.signature(extraction_pass.extract).bind(None, "", "", "", **extras)
        except TypeError as exc:
            raise TypeError(
                f"pass {extraction_pass.label!r}: "
                f"{extraction_pass.extract.__name__} does not accept the runner's "
                f"call signature - {exc}"
            ) from exc


_validate()


def run_extraction_passes(
    documents: list[PostcheckDocument], config: Any, settings: dict
) -> dict[str, int]:
    """Run each applicable pass over each document. Returns calls made per pass.

    The budget is a hard ceiling on LLM calls per review; a document skipped
    because of it records that as its error, so the reason reaches the report
    instead of looking like an extraction that returned nothing.

    A pass that costs nothing for this document runs whether or not an LLM is
    configured. That is not an optimisation: a tax-filing XML carries the
    figures already, and refusing to read them because no model was wired would
    report missing data about a file sitting right there.
    """

    remaining = config.max_extraction_calls
    photos_left = getattr(config, "max_photo_calls", config.max_extraction_calls)
    calls: dict[str, int] = {p.label: 0 for p in EXTRACTION_PASSES}

    vision_passes = {p.label for p in EXTRACTION_PASSES if p.reads_file}

    for document in documents:
        readable = document.extraction_status == "success" and document.content.strip()
        for extraction_pass in EXTRACTION_PASSES:
            if not readable and extraction_pass.label not in vision_passes:
                continue
            if not document.document_type:
                continue
            if not extraction_pass.applies_to(document.document_type):
                continue

            llm = getattr(config, extraction_pass.llm_attr)
            spends = extraction_pass.spends_llm_call(document)

            if extraction_pass.reads_file and spends and photos_left <= 0:
                setattr(
                    document, extraction_pass.error_attr,
                    f"vượt trần {config.max_photo_calls} ảnh mỗi hồ sơ nên chưa đọc ảnh này",
                )
                continue

            if spends:
                if llm is None:
                    setattr(
                        document,
                        extraction_pass.error_attr,
                        f"chưa cấu hình LLM cho pass '{extraction_pass.label}'",
                    )
                    continue
                if remaining <= 0:
                    setattr(
                        document,
                        extraction_pass.error_attr,
                        f"vượt trần {config.max_extraction_calls} lần gọi LLM mỗi hồ sơ",
                    )
                    continue
                remaining -= 1

            # The chain is None when no LLM is configured. The extract functions
            # accept that: run_extraction returns the "no LLM" message, and the
            # financial-statement pass reads an XML before it ever looks at the
            # chain.
            chain = extraction_pass.build_chain(llm) if llm is not None else None
            extras = (
                {"vocabulary": photo_vocabulary(settings),
                 "max_images": getattr(config, "max_photo_images", 12)}
                if extraction_pass.reads_file else {}
            )
            result, error = extraction_pass.extract(
                chain, document.filename, document.content, document.path, **extras
            )
            setattr(document, extraction_pass.result_attr, result)
            setattr(document, extraction_pass.error_attr, error)
            if result is not None and spends:
                calls[extraction_pass.label] += 1
                if extraction_pass.reads_file:
                    photos_left -= 1

    return calls
