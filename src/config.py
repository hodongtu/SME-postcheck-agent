"""LLM client factory + runtime Config.

build_llm is unchanged from SME_creditmemo: fail fast, naming the environment
variable that is missing, rather than quietly running on some default model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from langchain_openai import ChatOpenAI


def build_llm(
    model_env: str,
    temperature: float = 0.0,
    timeout_env: str = "LLM_TIMEOUT_SECONDS",
    max_tokens_env: str = "LLM_MAX_TOKENS",
):
    """Build one ChatOpenAI client from environment variables."""

    model = os.getenv(model_env, "")
    if not model:
        raise ValueError(
            f"{model_env} is not set; add it to .env or point this pass at a "
            f"variable that is"
        )
    return ChatOpenAI(
        model=model,
        base_url=os.getenv("OPENAI_API_BASE"),
        temperature=temperature,
        timeout=float(os.getenv(timeout_env, "60")),
        max_retries=int(os.getenv("LLM_CLIENT_MAX_RETRIES", "1")),
        max_tokens=int(os.getenv(max_tokens_env, "4096")),
    )


@dataclass
class Config:
    """Runtime config for one post-check review.

    Everything defaults to None on purpose: an unwired system must report
    insufficient data rather than guess. All 31 rules still run with every LLM
    and the executor set to None - every conclusion is simply "not checked".
    """

    # The four extraction passes, reused from SME_creditmemo
    financial_statement_llm: Any = None
    proposal_llm: Any = None
    sitevisit_llm: Any = None
    sitevisit_photo_llm: Any = None
    # The two commentary paragraphs in BRD 2.2 and 2.4
    commentary_llm: Any = None
    enable_commentary: bool = True
    # System queries: callable(sql, params) -> list[dict]
    query_executor: Any = None

    # Below this, a document is left unidentified rather than guessed. A CIC
    # report routed to the wrong subject would put the owner's debt group on the
    # customer, so an uncertain match must become missing data, not a guess.
    document_classifier_min_confidence: float = 0.60

    max_files: int = 50
    max_chars_per_document: int = 120_000
    # One call per (document, applicable pass). The real spend ceiling of a run.
    max_extraction_calls: int = 40
    # A separate ceiling for photographs. One dossier can carry dozens, and each
    # is a vision call - without this they would eat the whole extraction budget
    # and starve the passes that read the actual documents.
    max_photo_calls: int = 12
    # Photo dossiers usually arrive as ONE PDF, and one page of it often holds
    # several photographs - so the real size is the image count, not the file
    # count and not the page count. Images beyond this are reported, not dropped
    # silently.
    max_photo_images: int = 12
    ocr_timeout_seconds: float | None = None
