"""Every rule must catch its own violation.

Two violating fixtures together must cover the whole suite: case_broken keeps a
valid program so the rules downstream of P01 still run, and
case_broken_program exists purely so P01 has a violation. A rule absent from
the union of the two failure sets has no evidence that it works at all.

One rule cannot be violated by facts alone. C02 compares the industry against
config's `restricted_GSO`, which the business has not filled in, so with the real
settings there is no code for a fixture to match. Rather than leave the rule
untested until that list arrives, it is graded once more against a settings copy
carrying the fixture's own code - see CONFIG_LIST_RULES.
"""

from _harness import load_fixture, report
import copy
import sys


# rule id -> (settings key, the fact whose value must go into that list)
# For a rule that can only fail when a config list is non-empty.
CONFIG_LIST_RULES: dict[str, tuple[str, str]] = {
    "C02": ("restricted_GSO", "los.gso_code"),
}


def main() -> int:
    from src.rules.engine import run_rules
    from src.rules.registry import RULES
    from src.settings import get_settings

    settings = get_settings()
    problems: list[str] = []
    caught: set[str] = set()
    # What an uncovered rule said instead of failing. "no violating fixture for
    # E06" leaves the reader to guess whether the fixture is wrong or the rule
    # cannot fail at all; the sentence it returned usually says which.
    observed: dict[str, str] = {}

    for name in ("case_broken", "case_broken_program"):
        for finding in run_rules(RULES, load_fixture(name), settings):
            observed.setdefault(finding.rule_id, f"{finding.status}: {finding.observed}")
            if finding.status == "FAIL":
                caught.add(finding.rule_id)
            elif finding.status == "INSUFFICIENT_DATA":
                problems.append(
                    f"{name}/{finding.rule_id}: insufficient data in a complete fixture"
                )

    # Rules gated by an empty config list: populate the list from the fixture and
    # grade once more, so an empty policy list is not mistaken for a broken rule.
    for rule_id, (key, fact_path) in CONFIG_LIST_RULES.items():
        if rule_id in caught:
            problems.append(
                f"{rule_id} already fails with the real settings - remove it from "
                f"CONFIG_LIST_RULES rather than testing it against a fabricated list"
            )
            continue
        if settings.get(key):
            problems.append(
                f"settings['{key}'] is no longer empty, so {rule_id} should fail on a "
                f"fixture directly - remove it from CONFIG_LIST_RULES"
            )
            continue
        facts = load_fixture("case_broken")
        populated = copy.deepcopy(settings)
        populated[key] = [str(facts.get(fact_path))]
        rule = next(r for r in RULES if r.id == rule_id)
        for finding in run_rules((rule,), facts, populated):
            if finding.status == "FAIL":
                caught.add(rule_id)
            else:
                problems.append(
                    f"{rule_id}: with {key}={populated[key]} it still returned "
                    f"{finding.status}: {finding.observed}"
                )

    for rule in RULES:
        if rule.id not in caught:
            problems.append(
                f"no violating fixture for {rule.id} - it returned "
                f"{observed.get(rule.id, '(nothing)')}"
            )

    return report(problems, f"{len(caught)}/{len(RULES)} rules catch their own violation")


if __name__ == "__main__":
    sys.exit(main())
