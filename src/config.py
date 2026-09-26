"""LLM client factory + runtime Config. """

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

    financial_statement_llm: Any = None
    proposal_llm: Any = None
    sitevisit_llm: Any = None
    sitevisit_photo_llm: Any = None
    commentary_llm: Any = None
    enable_commentary: bool = True
    mask_pii: bool = True
    query_executor: Any = None
    document_classifier_min_confidence: float = 0.60

    max_files: int = 50
    max_chars_per_document: int = 120_000
    max_extraction_calls: int = 40
    max_photo_calls: int = 12
    max_photo_images: int = 12
    ocr_timeout_seconds: float | None = None
