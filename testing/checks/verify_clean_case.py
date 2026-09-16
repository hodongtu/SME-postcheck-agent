"""A clean dossier passes everything - catches a rule that can never pass."""

from _harness import load_fixture, report
import sys


def main() -> int:
    from src.rules.engine import run_rules, summarise
    from src.rules.registry import RULES
    from src.settings import get_settings

    findings = run_rules(RULES, load_fixture("case_clean"), get_settings())
    problems = [
        f"{f.rule_id} ({f.status}): {f.observed[:110]}"
        for f in findings if f.status != "PASS"
    ]
    counts = summarise(findings)
    return report(problems, f"{counts['PASS']}/{counts['TOTAL']} rules pass on a clean dossier")


if __name__ == "__main__":
    sys.exit(main())
