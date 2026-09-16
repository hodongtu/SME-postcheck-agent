"""Row helpers plus the import-time guard every query tool relies on."""

from __future__ import annotations

from typing import Any


def rows(executor: Any, sql: str, params: dict) -> list[dict]:
    return [dict(row) for row in (executor(sql, params) or [])]


def one_row(executor: Any, sql: str, params: dict) -> dict:
    found = rows(executor, sql, params)
    return found[0] if found else {}


def assert_no_model_arguments(tools: tuple[Any, ...]) -> None:
    """No tool may expose an argument a model could fill in.

    Same guard as the import-time assertion at the bottom of SME_creditmemo's
    src/agents/specialist.py. These tools reach customer credit data, so the
    parameters must come from the pipeline and nowhere else.
    """

    for tool_object in tools:
        schema = getattr(tool_object, "tool_call_schema", None)
        exposed = list(getattr(schema, "model_fields", {}) or {})
        if exposed:
            raise TypeError(
                f"Tool '{tool_object.name}' exposes {exposed} to the model. "
                f"Every argument must be Annotated[..., InjectedToolArg]."
            )
