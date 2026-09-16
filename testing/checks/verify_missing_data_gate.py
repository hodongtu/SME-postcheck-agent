"""Missing data must NEVER become a pass.

The most important check in the project. A rule suite that skips blank cells
reports green for the very regression that broke collection - the dossier looks
clean at the exact moment the data disappeared.

The gate is load-bearing, and measured: remove it, call check directly on a
full dossier with exactly one fact deleted, and 14 of 84 combinations return
PASS instead of failing. Among them C03 and O03 announcing that neither the
customer nor the owner is on the black or warning list, when that lookup
returned nothing at all, and E02 saying the same for the post-check date. 56 crash, 14 fail honestly. Rules crashing on
their own cannot be relied on.

This check runs the whole suite against an empty Facts with every check
function replaced by one that explodes. If the gate leaks for even one rule the
run dies with GateLeaked instead of returning results, so the check cannot pass
for the wrong reason.
"""

from _harness import report
import sys


class GateLeaked(AssertionError):
    """The runner called a check even though a fact was missing."""


def main() -> int:
    from dataclasses import replace

    from src.facts import Facts
    from src.rules.engine import NOT_CHECKED_PREFIX, run_rules
    from src.rules.registry import RULES
    from src.settings import get_settings

    def explode(facts, settings):
        raise GateLeaked("run_rules() called check() on missing data")

    armed = tuple(replace(rule, check=explode) for rule in RULES)
    findings = run_rules(armed, Facts(), get_settings())

    problems: list[str] = []
    for finding in findings:
        if finding.status != "INSUFFICIENT_DATA":
            problems.append(
                f"{finding.rule_id}: returned {finding.status} on empty facts, "
                f"expected INSUFFICIENT_DATA"
            )
        if not finding.missing:
            problems.append(f"{finding.rule_id}: did not name any missing fact")
        if NOT_CHECKED_PREFIX not in finding.observed:
            problems.append(f"{finding.rule_id}: observed text does not say it was not checked")

    if len(findings) != len(RULES):
        problems.append(f"only graded {len(findings)}/{len(RULES)} rules")

    return report(
        problems,
        f"{len(findings)}/{len(RULES)} rules return INSUFFICIENT_DATA on an empty "
        f"dossier; none pass and no check function was reached",
    )


if __name__ == "__main__":
    sys.exit(main())
