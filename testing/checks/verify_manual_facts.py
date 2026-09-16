"""The facts nobody collects are exactly the ones declared as such.

Six of the fields the BRD asks about have no extraction pass behind them, and
two more (the BL/WL lookup filed at review time) have no reader either. That is
a decision, not a defect - but a decision has to stay visible, so MANUAL_FACTS
names each one with a reason and this check holds the line in both directions:

  - a fact that quietly loses its collector but is not declared here is a bug;
  - a declared fact that gains a collector is also a bug, because the entry
    must then be deleted rather than left to mask real data.

Every declared fact must also actually block a rule. One that blocks nothing is
dead weight in FACT_KEYS.
"""

from _harness import ROOT, report
import sys


def main() -> int:
    from src.config import Config
    from src.facts import FACT_KEYS, MANUAL_FACTS, Facts
    from src.pipeline import assemble_document_facts, fetch_reference_data
    from src.rules.registry import RULES
    from src.settings import get_settings

    problems: list[str] = []

    # Run both collectors with nothing wired: whatever they never touch, even to
    # mark missing, is a fact with no collector at all.
    facts = Facts()
    facts.set("case.postcheck_date", "2025-09-14")
    assemble_document_facts(facts, [], get_settings())
    fetch_reference_data(facts, "0101234567", Config(), "2025-01-02", "2025-09-14")

    touched = set(facts.collected()) | set(facts.to_dict()["reasons"])
    untouched = set(FACT_KEYS) - touched

    undeclared = untouched - set(MANUAL_FACTS)
    if undeclared:
        problems.append(
            "no collector and not declared in MANUAL_FACTS: " + ", ".join(sorted(undeclared))
        )
    stale = set(MANUAL_FACTS) - untouched
    if stale:
        problems.append(
            "declared in MANUAL_FACTS but a collector now fills them, so the entries "
            "must be removed: " + ", ".join(sorted(stale))
        )

    for path, reason in MANUAL_FACTS.items():
        if path not in FACT_KEYS:
            problems.append(f"MANUAL_FACTS['{path}'] is not a declared fact")
        if not reason.strip():
            problems.append(f"MANUAL_FACTS['{path}'] has no reason")
        if not any(path in rule.needs for rule in RULES):
            problems.append(f"MANUAL_FACTS['{path}'] blocks no rule - it is dead weight")

    blocked = sorted({rule.id for rule in RULES
                      if set(rule.needs) & set(MANUAL_FACTS)})
    return report(
        problems,
        f"{len(MANUAL_FACTS)} facts have no collector, all declared with a reason; "
        f"they permanently block {len(blocked)} rules: {', '.join(blocked)}",
    )


if __name__ == "__main__":
    sys.exit(main())
