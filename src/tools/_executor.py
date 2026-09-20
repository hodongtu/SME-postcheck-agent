"""Row helpers plus the import-time guard every query tool relies on."""

from __future__ import annotations

from typing import Any


def rows(executor: Any, sql: str, params: dict) -> list[dict]:
    return [dict(row) for row in (executor(sql, params) or [])]


def one_row(executor: Any, sql: str, params: dict) -> dict:
    found = rows(executor, sql, params)
    return found[0] if found else {}


def assert_registry_is_sound(tools: tuple[Any, ...]) -> None:
    """No tool appears twice in the registry.

    A duplicate is silent in Python and wrong everywhere it is counted: the
    pipeline would call the query twice, and `verify_tools_are_used` would report
    a tool total that does not match the tools there are.
    """

    seen: set[str] = set()
    for tool_object in tools:
        name = getattr(tool_object, "name", repr(tool_object))
        if name in seen:
            raise TypeError(f"Tool '{name}' is listed twice in ALL_TOOLS.")
        seen.add(name)


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


def sqlite_executor(db_path: str) -> Any:
    """A `query_executor` backed by a SQLite file.

    Exists so the whole pipeline can be run against a fixed dataset with no
    database access: the dummy dataset under samples/dummy_db/ is what the
    end-to-end check grades. SQLite already understands the `:name` parameters
    the tools' SQL uses, and dates are stored as ISO text so BETWEEN and <=
    compare correctly by ordinary string ordering.

    One connection per call: these queries are small, reads only, and a
    short-lived connection keeps the executor safe to hand to anything.
    """

    import sqlite3

    def execute(sql: str, params: dict) -> list[dict]:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    return execute
