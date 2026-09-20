"""Every fact a rule declares exists, has a reader, and is classified correctly.

The classification half matters as much as the reader half. A fact carries two
labels that used to be one column: which of the business's seven groups it belongs
to, and who fills it. They drifted apart the moment the RM's online entries became
document data delivered by a query, and only the second one decides whether a fact
is marked missing when no database is wired - so a typo in either is a quiet
change to what the report says, not a crash.
"""

from _harness import report
import sys


def main() -> int:
    from src.facts import CATEGORIES, DELIVERIES, DISPLAY_ONLY_FACTS, FACT_KEYS
    from src.rules.registry import RULES

    problems: list[str] = []
    used: set[str] = set()

    for rule in RULES:
        if not rule.needs:
            problems.append(f"{rule.id}: empty needs")
        if len(set(rule.needs)) != len(rule.needs):
            problems.append(f"{rule.id}: a path appears twice in needs")
        for path in rule.needs:
            used.add(path)
            if path not in FACT_KEYS:
                problems.append(f"{rule.id}: needs '{path}', which is not in FACT_KEYS")

    for path in sorted(set(FACT_KEYS) - used - set(DISPLAY_ONLY_FACTS)):
        problems.append(f"FACT_KEYS declares '{path}' but no rule reads it - collected for nothing")

    # Both directions: a fact declared display-only that a rule now reads is a
    # stale declaration, and the declaration is the only thing keeping the check
    # above quiet about it.
    for path in sorted(set(DISPLAY_ONLY_FACTS) - set(FACT_KEYS)):
        problems.append(f"DISPLAY_ONLY_FACTS names '{path}', which is not in FACT_KEYS")
    for path in sorted(set(DISPLAY_ONLY_FACTS) & used):
        problems.append(
            f"'{path}' is declared display-only but a rule reads it - remove it from "
            f"DISPLAY_ONLY_FACTS so the no-reader check covers it again"
        )

    seen_categories: set[str] = set()
    for path, spec in FACT_KEYS.items():
        if len(spec) != 3 or not all(spec):
            problems.append(
                f"FACT_KEYS['{path}'] must be FactSpec(category, delivery, "
                f"description), all three non-empty"
            )
            continue
        seen_categories.add(spec.category)
        if spec.category not in CATEGORIES:
            problems.append(
                f"FACT_KEYS['{path}'] is in category {spec.category!r}, which is not "
                f"one of {list(CATEGORIES)} - a mistyped label becomes an eighth group "
                f"in the report with nobody noticing"
            )
        if spec.delivery not in DELIVERIES:
            problems.append(
                f"FACT_KEYS['{path}'] has delivery {spec.delivery!r}, expected one of "
                f"{list(DELIVERIES)}"
            )

    # The other direction: a category nothing uses means the business's list and
    # the code have drifted, and the report has a group that never prints.
    for category in CATEGORIES:
        if category not in seen_categories:
            problems.append(
                f"category {category!r} is declared but no fact belongs to it"
            )

    # The report's collection table names a category per row; it must be the one
    # the row's own facts carry, or the source column says the wrong thing.
    from src.report.render import COLLECTION_ROWS

    for part, rows in COLLECTION_ROWS.items():
        for label, declared, prefixes in rows:
            covered = {spec.category for path, spec in FACT_KEYS.items()
                       if any(path == p or path.startswith(p) for p in prefixes)}
            if covered and covered != {declared}:
                problems.append(
                    f"report row {part} {label!r} is labelled {declared!r} but covers "
                    f"facts from {sorted(covered)}"
                )

    return report(
        problems,
        f"{len(used)}/{len(FACT_KEYS)} facts are declared and read across "
        f"{len(seen_categories)} categories, {len(DISPLAY_ONLY_FACTS)} collected for "
        f"the report only",
    )


if __name__ == "__main__":
    sys.exit(main())
