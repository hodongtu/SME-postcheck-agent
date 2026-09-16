"""The grading layer must be pure Python.

Two architectural invariants, enforced by AST rather than by discipline:
  1. No rule file may touch an LLM, the network, or the system clock. A rule
     calling date.today() would grade the same dossier differently on two days
     - the review date is a fact, not the environment.
  2. No check function may return "INSUFFICIENT_DATA". Only run_rules decides
     that something was not checked.
"""

from _harness import ROOT, report
import ast
import sys


FORBIDDEN_IMPORTS = (
    "langchain", "langchain_core", "langchain_openai", "openai",
    "requests", "httpx", "urllib", "socket",
    "src.config", "src.pipeline", "src.tools", "src.passes",
)
FORBIDDEN_CALLS = {
    ("date", "today"), ("datetime", "now"), ("datetime", "today"),
    ("time", "time"), ("random", "random"),
}


def main() -> int:
    problems: list[str] = []
    rule_files = sorted((ROOT / "src" / "rules").glob("*.py"))

    for path in rule_files:
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                names = []
            for name in names:
                if any(name == banned or name.startswith(banned + ".")
                       for banned in FORBIDDEN_IMPORTS):
                    problems.append(f"{relative}: imports '{name}' - rules must be pure Python")

            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = getattr(node.func.value, "id", "")
                if (owner, node.func.attr) in FORBIDDEN_CALLS:
                    problems.append(
                        f"{relative}: calls {owner}.{node.func.attr}() - the review date "
                        f"must come from the fact 'case.postcheck_date', not the clock"
                    )

            if isinstance(node, ast.Constant) and node.value == "INSUFFICIENT_DATA":
                if path.name != "engine.py":
                    problems.append(
                        f"{relative}: mentions 'INSUFFICIENT_DATA' - only run_rules() may "
                        f"conclude that something was not checked"
                    )

    return report(problems, f"{len(rule_files)} files under src/rules/ are pure and deterministic")


if __name__ == "__main__":
    sys.exit(main())
