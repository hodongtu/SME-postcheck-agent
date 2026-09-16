"""Every fact a rule declares exists, and every declared fact has a reader."""

from _harness import report
import sys


def main() -> int:
    from src.facts import FACT_KEYS
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

    for path in sorted(set(FACT_KEYS) - used):
        problems.append(f"FACT_KEYS declares '{path}' but no rule reads it - collected for nothing")

    for path, meta in FACT_KEYS.items():
        if not isinstance(meta, tuple) or len(meta) != 2 or not all(meta):
            problems.append(f"FACT_KEYS['{path}'] must be (source, description), both non-empty")

    return report(problems, f"{len(used)}/{len(FACT_KEYS)} facts are declared and read")


if __name__ == "__main__":
    sys.exit(main())
