"""Rule declarations are well formed and printable.

Coverage against the BRD is verify_brd_coverage's job, since config/brd_map.yaml
owns that link. What is left here is hygiene on the rules themselves: unique
ids, a recognised id shape, a valid severity, and strings long enough to mean
something in the report a reviewer signs.
"""

from _harness import report
import re
import sys


RULE_ID = re.compile(r"^[VFPCOE]\d\d$")
MIN_TEXT = 10


def main() -> int:
    from collections import Counter
    from src.rules.engine import SEVERITY_LABELS
    from src.rules.registry import RULES

    problems: list[str] = []

    for rule_id, seen in Counter(rule.id for rule in RULES).items():
        if seen > 1:
            problems.append(f"rule id '{rule_id}' is used {seen} times")

    for rule in RULES:
        if not RULE_ID.match(rule.id):
            problems.append(f"'{rule.id}' does not match the id shape V/F/P/C/O/E + two digits")
        if rule.severity not in SEVERITY_LABELS:
            problems.append(f"{rule.id}: severity '{rule.severity}' has no label")
        for field in ("title", "expected"):
            if len(getattr(rule, field).strip()) < MIN_TEXT:
                problems.append(f"{rule.id}: {field} is too short to print in the report")
        if not callable(rule.check):
            problems.append(f"{rule.id}: check is not callable")

    groups = Counter(rule.id[0] for rule in RULES)
    return report(
        problems,
        f"{len(RULES)} rules are well formed: "
        + ", ".join(f"{letter}={n}" for letter, n in sorted(groups.items())),
    )


if __name__ == "__main__":
    sys.exit(main())
