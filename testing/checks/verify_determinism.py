"""Two runs over the same dossier must agree, character for character."""

from _harness import load_fixture, report
import sys


def main() -> int:
    from dataclasses import asdict
    from src.rules.engine import run_rules
    from src.rules.registry import RULES
    from src.settings import get_settings

    settings = get_settings()
    problems: list[str] = []

    for name in ("case_clean", "case_broken"):
        first = [asdict(f) for f in run_rules(RULES, load_fixture(name), settings)]
        second = [asdict(f) for f in run_rules(RULES, load_fixture(name), settings)]
        for left, right in zip(first, second):
            if left != right:
                problems.append(f"{name}/{left['rule_id']}: two runs disagree")

    return report(problems, "two runs over the same dossier match exactly")


if __name__ == "__main__":
    sys.exit(main())
