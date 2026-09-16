"""Every rule must catch its own violation.

Two violating fixtures together must cover the whole suite: case_broken keeps a
valid program so the rules downstream of P01 still run, and
case_broken_program exists purely so P01 has a violation. A rule absent from
the union of the two failure sets has no evidence that it works at all.
"""

from _harness import load_fixture, report
import sys


def main() -> int:
    from src.rules.engine import run_rules
    from src.rules.registry import RULES
    from src.settings import get_settings

    settings = get_settings()
    problems: list[str] = []
    caught: set[str] = set()

    for name in ("case_broken", "case_broken_program"):
        for finding in run_rules(RULES, load_fixture(name), settings):
            if finding.status == "FAIL":
                caught.add(finding.rule_id)
            elif finding.status == "INSUFFICIENT_DATA":
                problems.append(
                    f"{name}/{finding.rule_id}: insufficient data in a complete fixture"
                )

    uncovered = [rule.id for rule in RULES if rule.id not in caught]
    if uncovered:
        problems.append("no violating fixture for: " + ", ".join(uncovered))

    return report(problems, f"{len(caught)}/{len(RULES)} rules catch their own violation")


if __name__ == "__main__":
    sys.exit(main())
