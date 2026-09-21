"""The run is the graph, the graph is linear, and its order is load-bearing.

Moving the steps into LangGraph buys one thing: the order stops being implied by
the order of statements inside a function and becomes something declared. That is
only worth anything if the declaration is checked, so this asserts three things.

The third is the point. Two of the edges carry a dependency that does NOT raise
when reversed - both orders run to completion, one just produces worse facts and
a report that quietly reports a checkable criterion as unchecked.
A reversed edge like that survives every other check in this suite.

It is measured on the customer LOS asks for NO site visit, because that is the
only case where the dependency shows: the photo collector reads
los.is_site_visit to decide that "no photographs" is an answer rather than a gap,
and with the collectors reversed that fact is not there yet. Graded on the other
customer the swap changes nothing, which is exactly how a check can look like it
is protecting something while protecting nothing.
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
    "extract",
    "start_facts",
    "collect_reference_data",
    "assemble_document_facts",
    "grade",
    "narrate",
    "render",
)


def main() -> int:
    from src.config import Config
    from src.graph import NODES, PostcheckState, build_postcheck_graph
    from src.tools._executor import sqlite_executor

    problems: list[str] = []

    declared = [name for name, _ in NODES]
    if declared != list(EXPECTED_ORDER):
        problems.append(
            f"src/graph.py declares {declared}, this check expects "
            f"{list(EXPECTED_ORDER)} - if the change is deliberate, record it here"
        )

    drawn = build_postcheck_graph().get_graph()
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
        if len(targets) > 1:
            problems.append(f"node {source!r} branches to {sorted(targets)}")

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
    from langgraph.graph import END, START, StateGraph

    swapped_order = list(EXPECTED_ORDER)
    a = swapped_order.index("collect_reference_data")
    b = swapped_order.index("assemble_document_facts")
    swapped_order[a], swapped_order[b] = swapped_order[b], swapped_order[a]

    functions = dict(NODES)
    builder = StateGraph(PostcheckState)
    for name in swapped_order:
        builder.add_node(name, functions[name])
    builder.add_edge(START, swapped_order[0])
    for earlier, later in zip(swapped_order, swapped_order[1:]):
        builder.add_edge(earlier, later)
    builder.add_edge(swapped_order[-1], END)

    def grade(graph) -> dict:
        return graph.invoke({
            "case_dir": str(ROOT / "samples" / "case_demo"),
            "tax_code": NO_SITE_VISIT_CUSTOMER,
            "approval_date": "2026-04-01",
            "postcheck_date": "2026-09-15",
            "config": Config(query_executor=sqlite_executor(
                str(ROOT / "samples" / "dummy_db" / "postcheck_dummy.sqlite"))),
            "settings": __import__("src.settings", fromlist=["x"]).get_settings(),
        })

    correct = grade(build_postcheck_graph())["counts"]
    reversed_counts = grade(builder.compile())["counts"]

    if reversed_counts["INSUFFICIENT_DATA"] <= correct["INSUFFICIENT_DATA"]:
        problems.append(
            f"swapping collect_reference_data and assemble_document_facts changed "
            f"nothing ({correct} vs {reversed_counts}) - the declared order is not "
            f"actually load-bearing, so nothing here protects it"
        )
    if correct["FAIL"] != reversed_counts["FAIL"]:
        problems.append(
            f"the swap changed FAIL counts ({correct['FAIL']} vs "
            f"{reversed_counts['FAIL']}) - it was expected to cost coverage, not to "
            f"flip a verdict, so the effect is bigger than this check describes"
        )

    return report(
        problems,
        f"{len(declared)} nodes in one linear path; reversing the two collectors "
        f"costs {reversed_counts['INSUFFICIENT_DATA'] - correct['INSUFFICIENT_DATA']} "
        f"criteria, which is why the order is declared rather than implied",
    )


if __name__ == "__main__":
    sys.exit(main())
