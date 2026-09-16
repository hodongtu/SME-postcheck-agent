"""One absent fact is enough to stop a rule concluding.

Complements verify_missing_data_gate, where the dossier is entirely empty. Here
the dossier is complete and one fact is removed at a time - the case that
actually happens, when a single query fails while everything else succeeds.
"""

from _harness import load_fixture, report
import sys


def main() -> int:
    from src.facts import Facts
    from src.rules.engine import run_rules
    from src.rules.registry import RULES
    from src.settings import get_settings

    settings = get_settings()
    base = load_fixture("case_clean").to_dict()["values"]
    problems: list[str] = []
    combinations = 0

    for rule in RULES:
        for path in rule.needs:
            facts = Facts({key: value for key, value in base.items() if key != path})
            facts.mark_missing(path, "removed to exercise the missing-data gate")
            finding = run_rules((rule,), facts, settings)[0]
            combinations += 1
            if finding.status != "INSUFFICIENT_DATA":
                problems.append(
                    f"{rule.id}: concluded {finding.status} with '{path}' missing "
                    f"- {finding.observed[:80]}"
                )

    return report(
        problems,
        f"{combinations} (rule x fact) combinations all stop at INSUFFICIENT_DATA "
        f"when the fact is removed",
    )


if __name__ == "__main__":
    sys.exit(main())
