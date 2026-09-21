"""The run is the graph, the graph is linear, and its order is load-bearing.

Moving the steps into LangGraph buys one thing: the order stops being implied by
the order of statements inside a function and becomes something declared. That is
only worth anything if the declaration is checked, so this asserts three things.

The third is the point. Two of the edges carry a dependency that does NOT raise
when reversed - both orders run to completion, one just produces worse facts and
a report that quietly reports a checkable criterion as unchecked.
A reversed edge like that survives every other check in this suite.

Reversing them may raise or may merely degrade, and both count. Which one it is
depends on where the Facts object gets created: while collect_reference_data
creates it, running the other collector first dies outright; move that and the
failure becomes quiet again - the photo collector reads los.is_site_visit to
decide whether "no photographs" is an answer or a gap, and would find it absent.
The check accepts either outcome and refuses only the third: a reversal that runs
fine and grades the same, which would mean the declared order is decoration.

It is measured on the customer LOS asks for NO site visit, because that is where
the quiet version of the dependency shows. Graded on the other customer the swap
changes nothing at all.
"""

from _harness import ROOT, report
import sys


# The order the pipeline contracts to. Changing it is a decision; this list is
# where the decision is recorded.
# The dummy customer LOS does not ask for a site visit. See the module docstring
# for why the ordering check has to use this one.
NO_SITE_VISIT_CUSTOMER = "0209999999"

EXPECTED_ORDER = (
    "read_documents",
    "extract_documents",
    "collect_reference_data",
    "assemble_document_facts",
    "grade_criteria",
    "write_commentary",
    "render_report",
)

# grade_criteria routes: with no commentary model it goes straight to the report.
BRANCHING_NODE = "grade_criteria"


def main() -> int:
    from src.config import Config
    from src.pipeline import NODE_ORDER, PostcheckSupervisor
    from src.tools._executor import sqlite_executor

    problems: list[str] = []

    declared = list(NODE_ORDER)
    if declared != list(EXPECTED_ORDER):
        problems.append(
            f"src/pipeline.py declares {declared}, this check expects "
            f"{list(EXPECTED_ORDER)} - if the change is deliberate, record it here"
        )

    def supervisor() -> PostcheckSupervisor:
        return PostcheckSupervisor(Config(query_executor=sqlite_executor(
            str(ROOT / "samples" / "dummy_db" / "postcheck_dummy.sqlite"))))

    drawn = supervisor().workflow_graph.get_graph()
    wired = {node.id for node in drawn.nodes.values()} - {"__start__", "__end__"}
    if wired != set(declared):
        problems.append(
            f"nodes declared but not wired: {sorted(set(declared) - wired)}; "
            f"wired but not declared: {sorted(wired - set(declared))}"
        )

    # Linear: one way in, one way out, no branch nobody meant to add.
    successors: dict[str, list[str]] = {}
    for edge in drawn.edges:
        successors.setdefault(edge.source, []).append(edge.target)
    for source, targets in sorted(successors.items()):
        if len(targets) > 1 and source != BRANCHING_NODE:
            problems.append(f"node {source!r} branches to {sorted(targets)}")
    if len(successors.get(BRANCHING_NODE, [])) < 2:
        problems.append(
            f"{BRANCHING_NODE!r} no longer branches - the commentary step has "
            f"become unconditional, so a run with no model calls it for nothing"
        )

    # Stop here if the shape is already wrong. Running a graph that is not the
    # one declared proves nothing about the declared one, and it tends to die
    # with a KeyError from some node reading a key its predecessor never wrote -
    # a crash instead of the finding that explains it.
    if problems:
        return report(problems, "")

    # --- the order is load-bearing -----------------------------------------
    # Build the same graph with the two collectors swapped and grade the demo
    # dossier with it. It must come out WORSE - if it does not, the declared
    # order is decoration and this check is protecting nothing.
    from langgraph.graph import END, StateGraph

    from src.types import PostcheckGraphState

    swapped_order = list(EXPECTED_ORDER)
    a = swapped_order.index("collect_reference_data")
    b = swapped_order.index("assemble_document_facts")
    swapped_order[a], swapped_order[b] = swapped_order[b], swapped_order[a]

    def reordered(boss: PostcheckSupervisor):
        """The same nodes, the two collectors the other way round."""

        builder = StateGraph(PostcheckGraphState)
        for name in swapped_order:
            builder.add_node(name, getattr(boss, f"_graph_{name}"))
        builder.set_entry_point(swapped_order[0])
        for earlier, later in zip(swapped_order, swapped_order[1:]):
            builder.add_edge(earlier, later)
        builder.add_edge(swapped_order[-1], END)
        return builder.compile()

    def grade(graph) -> dict:
        return graph.invoke({
            "case_dir": str(ROOT / "samples" / "case_demo"),
            "tax_code": NO_SITE_VISIT_CUSTOMER,
            "approval_date": "2026-04-01",
            "postcheck_date": "2026-09-15",
            "steps": [],
            "commentary_enabled": False,
        })

    boss = supervisor()
    correct = grade(boss.workflow_graph)["counts"]

    outcome = ""
    try:
        reversed_counts = grade(reordered(boss))["counts"]
    except Exception as exc:                          # noqa: BLE001
        reversed_counts = None
        outcome = f"raises {type(exc).__name__}"
    else:
        if reversed_counts["INSUFFICIENT_DATA"] > correct["INSUFFICIENT_DATA"]:
            outcome = (
                f"costs "
                f"{reversed_counts['INSUFFICIENT_DATA'] - correct['INSUFFICIENT_DATA']} "
                f"criteria"
            )

    if not outcome:
        problems.append(
            f"swapping collect_reference_data and assemble_document_facts produced a "
            f"working run with the same coverage ({correct} vs {reversed_counts}) - "
            f"the declared order is not load-bearing, so nothing here protects it"
        )



    return report(
        problems,
        f"{len(declared)} nodes, one branch at {BRANCHING_NODE}; reversing the two "
        f"collectors {outcome}, which is why the order is declared rather than "
        f"implied",
    )


if __name__ == "__main__":
    sys.exit(main())
