"""The post-check workflow as a LangGraph state machine.

Same shape as SME_creditmemo's src/agents/supervisor.py: a class holds the
config, builds the graph once, and each step is a `_graph_*` method that takes
the state and returns it. The order of the steps is declared in one place
instead of being implied by the order of statements inside a function.

Two edges carry a dependency that does NOT raise when reversed:

  collect_reference_data BEFORE assemble_document_facts
      the photo collector reads los.is_site_visit to decide whether "no
      photographs" is an answer or a gap.

  mark_manual_facts AFTER both collectors
      it marks what nobody filled, so everyone has to have finished.

One real branch: commentary. With no model wired the run goes straight to
render, and the report says so rather than carrying two empty sections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from src.facts import MISSING, Facts
from src.passes import run_extraction_passes
from src.report.commentary import build_commentary
from src.report.render import render_report
from src.rules.engine import run_rules, summarise
from src.rules.registry import RULES
from src.settings import get_settings
from src.types import PostcheckGraphState

# The order the workflow contracts to. Read by testing/checks/verify_graph.py,
# which builds a reordered copy and shows the order is load-bearing.
NODE_ORDER: tuple[str, ...] = (
    "read_documents",
    "extract_documents",
    "collect_reference_data",
    "assemble_document_facts",
    "grade_criteria",
    "write_commentary",
    "render_report",
)


class PostcheckSupervisor:
    """Runs one post-check review."""

    def __init__(self, config: Any):
        self.config = config
        self.settings = get_settings()
        self.workflow_graph = self._build_workflow_graph()

    def _build_workflow_graph(self):
        """Build the deterministic LangGraph post-check workflow."""

        workflow = StateGraph(PostcheckGraphState)
        workflow.add_node("read_documents", self._graph_read_documents)
        workflow.add_node("extract_documents", self._graph_extract_documents)
        workflow.add_node("collect_reference_data", self._graph_collect_reference_data)
        workflow.add_node("assemble_document_facts", self._graph_assemble_document_facts)
        workflow.add_node("grade_criteria", self._graph_grade_criteria)
        workflow.add_node("write_commentary", self._graph_write_commentary)
        workflow.add_node("render_report", self._graph_render_report)

        workflow.set_entry_point("read_documents")
        workflow.add_edge("read_documents", "extract_documents")
        workflow.add_edge("extract_documents", "collect_reference_data")
        workflow.add_edge("collect_reference_data", "assemble_document_facts")
        workflow.add_edge("assemble_document_facts", "grade_criteria")
        workflow.add_conditional_edges(
            "grade_criteria",
            self._graph_commentary_wanted,
            {"skip": "render_report", "write": "write_commentary"},
        )
        workflow.add_edge("write_commentary", "render_report")
        workflow.add_edge("render_report", END)

        return workflow.compile()

    # ── Graph nodes, in the order the workflow runs them ──────────────────

    def _graph_read_documents(
        self, state: PostcheckGraphState
    ) -> PostcheckGraphState:
        """Read every file in the case folder, whatever its format."""

        from src.pipeline import read_case_documents

        documents = read_case_documents(Path(state["case_dir"]), self.config)
        unreadable = sum(1 for d in documents if d.extraction_status != "success")
        steps = state.get("steps", [])
        steps.append(
            f"Đọc {len(documents)} tài liệu"
            + (f", {unreadable} chưa đọc được nội dung" if unreadable else "")
        )
        return {**state, "documents": documents, "steps": steps}

    def _graph_extract_documents(
        self, state: PostcheckGraphState
    ) -> PostcheckGraphState:
        """Run each extraction pass over the documents it applies to."""

        calls = run_extraction_passes(state["documents"], self.config, self.settings)
        spent = sum(calls.values())
        steps = state.get("steps", [])
        steps.append(
            f"Trích xuất: {spent} lượt gọi mô hình"
            + (f" ({', '.join(f'{k} {v}' for k, v in calls.items() if v)})" if spent else "")
        )
        return {**state, "extraction_calls": calls, "steps": steps}

    def _graph_collect_reference_data(
        self, state: PostcheckGraphState
    ) -> PostcheckGraphState:
        """Query every system. Runs BEFORE the dossier facts - see module docstring."""

        from src.pipeline import fetch_reference_data

        facts = Facts()
        facts.set("case.postcheck_date", state["postcheck_date"],
                  reason="chưa truyền ngày rà soát vào run_postcheck")
        fetch_reference_data(facts, state["tax_code"], self.config,
                             state["approval_date"], state["postcheck_date"],
                             self.settings)
        collected = len(facts.collected())
        steps = state.get("steps", [])
        steps.append(f"Truy vấn hệ thống: {collected} fact có giá trị")
        return {**state, "facts": facts, "steps": steps}

    def _graph_assemble_document_facts(
        self, state: PostcheckGraphState
    ) -> PostcheckGraphState:
        """Read the dossier into facts, then mark what nobody collected."""

        from src.pipeline import assemble_document_facts

        facts = state["facts"]
        before = len(facts.collected())
        assemble_document_facts(facts, state["documents"], self.settings)
        facts.mark_manual_facts_missing()
        steps = state.get("steps", [])
        steps.append(
            f"Lắp fact từ chứng từ: thêm {len(facts.collected()) - before} fact"
        )
        return {**state, "steps": steps}

    def _graph_grade_criteria(
        self, state: PostcheckGraphState
    ) -> PostcheckGraphState:
        """Grade every rule. Pure Python over the facts - no model, no network."""

        findings = run_rules(RULES, state["facts"], self.settings)
        counts = summarise(findings)
        steps = state.get("steps", [])
        steps.append(
            f"Chấm {counts['TOTAL']} tiêu chí: {counts['PASS']} đạt, "
            f"{counts['FAIL']} không đạt, {counts['INSUFFICIENT_DATA']} thiếu dữ liệu"
        )
        return {**state, "findings": findings, "counts": counts, "steps": steps}

    @staticmethod
    def _graph_commentary_wanted(state: PostcheckGraphState) -> str:
        """Whether this run writes the two commentary paragraphs.

        Decided in `run`, from the flag AND whether a model is wired: with no
        model the node would call build_commentary only to be handed {} back, and
        the step log would report writing nothing as if it were work done.
        """

        return "write" if state.get("commentary_enabled") else "skip"

    def _graph_write_commentary(
        self, state: PostcheckGraphState
    ) -> PostcheckGraphState:
        """The only model call outside extraction: the two BRD commentary sections."""

        commentary = build_commentary(state["findings"], self.config.commentary_llm)
        steps = state.get("steps", [])
        steps.append(f"Viết nhận định cho {len(commentary)} mục")
        return {**state, "commentary": commentary, "steps": steps}

    def _graph_render_report(
        self, state: PostcheckGraphState
    ) -> PostcheckGraphState:
        """Fill the report template from the findings."""

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
        report = render_report(state["findings"], meta,
                               state.get("commentary") or {}, facts=facts)
        steps = state.get("steps", [])
        if not state.get("commentary"):
            steps.append("Bỏ qua nhận định: chưa cấu hình commentary_llm")
        steps.append(f"Kết xuất báo cáo: {len(report)} ký tự")
        return {**state, "report_markdown": report, "steps": steps}

    # ── Entry point ───────────────────────────────────────────────────────

    def run(
        self,
        case_dir: str | Path,
        tax_code: str,
        approval_date: str,
        postcheck_date: str,
    ) -> dict:
        """Invoke the graph and hand back its final state."""

        return self.workflow_graph.invoke({
            "case_dir": str(case_dir),
            "tax_code": tax_code,
            "approval_date": approval_date,
            "postcheck_date": postcheck_date,
            "steps": [],
            "commentary_enabled": bool(
                self.config.enable_commentary and self.config.commentary_llm
            ),
        })


def build_postcheck_graph(config: Any = None):
    """The compiled graph on its own, for drawing it or inspecting its shape."""

    from src.config import Config

    return PostcheckSupervisor(config or Config()).workflow_graph
