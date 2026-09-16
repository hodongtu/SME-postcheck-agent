"""The tool registry tells the truth about what the pipeline calls.

Two ways a query layer rots quietly, and this closes both:

  - a tool sits in ALL_TOOLS that nothing invokes. It reads as wired, so the
    facts it was supposed to fill look collected when nobody asked for them.
  - a tool is defined under src/tools/ and belongs to no list at all, so it is
    dead code nobody notices.

PARKED names the tools that exist without being wired, the same way
MANUAL_FACTS names the facts nobody collects: an exception has to be visible to
stay a decision rather than becoming an accident.
"""

from _harness import ROOT, report
import ast
import sys


# Nothing is parked. A tool defined but wired to nothing was removed rather than
# explained: when a rule needs it, the query comes back with the rule.
PARKED: set[str] = set()


def _attribute_names(path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def _defined_tools() -> dict[str, str]:
    """Every @tool-decorated function under src/tools/, mapped to its file."""

    found: dict[str, str] = {}
    for path in sorted((ROOT / "src" / "tools").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if getattr(target, "id", "") == "tool":
                    found[node.name] = path.name
    return found


def main() -> int:
    from src.tools.registry import ALL_TOOLS

    problems: list[str] = []
    called = _attribute_names(ROOT / "src" / "pipeline.py")
    registered = {tool_object.name for tool_object in ALL_TOOLS}
    defined = _defined_tools()

    for name in sorted(registered):
        if name not in called:
            problems.append(
                f"'{name}' is in ALL_TOOLS but src/pipeline.py never calls it - "
                f"either wire it or move it to PARKED"
            )

    for name, filename in sorted(defined.items()):
        if name not in registered and name not in PARKED:
            problems.append(
                f"'{name}' is defined in src/tools/{filename} but is in neither "
                f"ALL_TOOLS nor PARKED - dead code"
            )

    for name in sorted(PARKED):
        if name in registered:
            problems.append(f"'{name}' is both PARKED and registered - pick one")
        if name not in defined:
            problems.append(f"PARKED names '{name}', which is not defined under src/tools/")

    return report(
        problems,
        f"{len(registered)} registered tools are all called by the pipeline, "
        f"and nothing under src/tools/ is defined without being wired",
    )


if __name__ == "__main__":
    sys.exit(main())
