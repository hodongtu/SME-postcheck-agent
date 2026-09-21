"""The post-check run as a LangGraph state machine.

Seven nodes, one edge each, no branching. The value is not routing - it is that
the steps and the order between them are declared in one place instead of being
implied by the order of statements inside a function.

Two orderings here are load-bearing and easy to break by accident:

  collect_reference_data BEFORE assemble_document_facts
      the photo collector reads los.is_site_visit, and the checklist rule reads
      it too; run the other way round and both go missing.

  mark_manual_facts AFTER both collectors
      it marks what nobody filled, so it has to run when everyone has finished.

`build_postcheck_graph().get_graph().draw_mermaid()` prints the diagram from the
graph itself, so a picture of the flow cannot drift from the flow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from src.facts import MISSING, Facts
from src.passes import run_extraction_passes
from src.report.commentary import build_commentary
from src.report.render import render_report
from src.rules.engine import Finding, run_rules, summarise
from src.rules.registry import RULES
from src.types import PostcheckDocument


class PostcheckState(TypedDict, total=False):
    """Everything a node may read or write."""

    case_dir: str
    tax_code: str
    approval_date: str
    postcheck_date: str
    config: Any
    settings: dict

    documents: list[PostcheckDocument]
    extraction_calls: dict[str, int]
    facts: Facts
    findings: list[Finding]
    commentary: dict[str, str]
    report_markdown: str
    counts: dict[str, int]


def _read_documents(state: PostcheckState) -> dict:
    from src.pipeline import read_case_documents

    return {"documents": read_case_documents(Path(state["case_dir"]), state["config"])}


def _extract(state: PostcheckState) -> dict:
    return {"extraction_calls": run_extraction_passes(
        state["documents"], state["config"], state["settings"]
    )}


def _start_facts(state: PostcheckState) -> dict:
    facts = Facts()
    facts.set("case.postcheck_date", state["postcheck_date"],
              reason="chưa truyền ngày rà soát vào run_postcheck")
    return {"facts": facts}


def _collect_reference_data(state: PostcheckState) -> dict:
    from src.pipeline import fetch_reference_data

    fetch_reference_data(state["facts"], state["tax_code"], state["config"],
                         state["approval_date"], state["postcheck_date"],
                         state["settings"])
    return {}


def _assemble_document_facts(state: PostcheckState) -> dict:
    from src.pipeline import assemble_document_facts

    assemble_document_facts(state["facts"], state["documents"], state["settings"])
    state["facts"].mark_manual_facts_missing()
    return {}


def _grade(state: PostcheckState) -> dict:
    findings = run_rules(RULES, state["facts"], state["settings"])
    return {"findings": findings, "counts": summarise(findings)}


def _narrate(state: PostcheckState) -> dict:
    config = state["config"]
    return {"commentary": (
        build_commentary(state["findings"], config.commentary_llm)
        if config.enable_commentary else {}
    )}


def _render(state: PostcheckState) -> dict:
    facts = state["facts"]

    def or_dash(path: str, fallback: str = "—") -> str:
        value = facts.get(path)
        return str(value) if value is not MISSING else fallback

    meta = {
        "customer_name": or_dash("los.customer_name"),
        "tax_code": or_dash("los.tax_code", state["tax_code"]),
        "program": or_dash("los.program"),
        "postcheck_date": state["postcheck_date"],
    }
    return {"report_markdown": render_report(
        state["findings"], meta, state["commentary"], facts=facts
    )}


NODES = (
    ("read_documents", _read_documents),
    ("extract", _extract),
    ("start_facts", _start_facts),
    ("collect_reference_data", _collect_reference_data),
    ("assemble_document_facts", _assemble_document_facts),
    ("grade", _grade),
    ("narrate", _narrate),
    ("render", _render),
)


def build_postcheck_graph() -> Any:
    """The compiled graph. One linear path; the order is the contract."""

    builder = StateGraph(PostcheckState)
    for name, function in NODES:
        builder.add_node(name, function)

    builder.add_edge(START, NODES[0][0])
    for (earlier, _), (later, _) in zip(NODES, NODES[1:]):
        builder.add_edge(earlier, later)
    builder.add_edge(NODES[-1][0], END)

    return builder.compile()
