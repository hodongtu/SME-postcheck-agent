"""A failed criterion must be impossible to miss, in Markdown and in the PDF.

The report is a compliance document read under time pressure: 19 failures sat in
a 40-row table marked only by a bold phrase in the middle column. This grades the
three devices that fix that, and it grades them against the findings themselves -
a highlight that drifts out of step with the verdicts is worse than none, because
it teaches the reader to trust the colour.
"""

from _harness import ROOT, report
import sys

CASES = (("0201123795", "hồ sơ sạch"), ("0209999999", "hồ sơ ngoài ngưỡng"))


def main() -> int:
    from src.config import Config
    from src.pipeline import run_postcheck
    from src.report.render import STATUS_MARK
    from src.tools._executor import sqlite_executor
    from src.utils.report.report_style import highlight_failed_rows

    database = ROOT / "samples" / "dummy_db" / "postcheck_dummy.sqlite"
    if not database.exists():
        return report(["samples/dummy_db/postcheck_dummy.sqlite is missing; "
                       "run make_dummy_db.py"], "")

    problems: list[str] = []
    counted: list[str] = []

    for tax_code, label in CASES:
        result = run_postcheck(
            case_dir=ROOT / "samples" / "case_demo",
            config=Config(query_executor=sqlite_executor(str(database))),
            tax_code=tax_code,
            approval_date="2026-04-01",
            postcheck_date="2026-09-15",
        )
        markdown = result.report_markdown
        failures = [f for f in result.findings if f.status == "FAIL"]
        counted.append(f"{label}: {len(failures)}")

        for finding in failures:
            row = f"| **{finding.rule_id}** |"
            if row not in markdown:
                problems.append(
                    f"{label}/{finding.rule_id}: failed, but its row is not marked "
                    f"in the code column"
                )
            if f"- **{finding.rule_id}**" not in markdown:
                problems.append(
                    f"{label}/{finding.rule_id}: failed, but the summary at the top "
                    f"does not list it"
                )
        for finding in result.findings:
            if finding.status != "FAIL" and f"| **{finding.rule_id}** |" in markdown:
                problems.append(
                    f"{label}/{finding.rule_id}: marked as a failure although it is "
                    f"{finding.status}"
                )

        # The PDF path: one tagged row per failure, no more and no fewer. A stray
        # tag would tint a passing row, which is the worse direction of wrong.
        rows = "".join(
            f"<tr><td>{f.rule_id}</td><td>{STATUS_MARK[f.status]}</td></tr>"
            for f in result.findings
        )
        tagged = highlight_failed_rows(f"<table>{rows}</table>").count('class="fail"')
        if tagged != len(failures):
            problems.append(
                f"{label}: {tagged} row(s) tinted for the PDF but {len(failures)} "
                f"criteria failed"
            )

    return report(
        problems,
        f"failures marked in the code column, listed in the summary and tinted in "
        f"the PDF, with nothing passing marked ({'; '.join(counted)})",
    )


if __name__ == "__main__":
    sys.exit(main())
