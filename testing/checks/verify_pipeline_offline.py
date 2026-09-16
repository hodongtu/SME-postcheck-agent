"""With no LLM and no database, nothing is graded that cannot be.

The earlier version of this check asserted zero passes, which happened to hold
only because the old sample dossier also broke the file-format rule. That was
the wrong assertion: P03 reads file names, so it is decidable with nothing
wired at all, and forcing it to report insufficient data would be dishonest in
the other direction.

What must hold is narrower and truer: a rule may pass only if every fact it
needs is obtainable without an extraction pass and without a query. Everything
else must stop at insufficient data, naming what is missing.
"""

from _harness import ROOT, report
import sys


# Everything the pipeline can fill with no LLM and no executor, by source:
#
#   file names in the upload boxes      the checklist and the format list
#   the arguments of the run itself     the review date
#   a tax-filing XML in the dossier     the whole financial statement, read by
#                                       parse_tax_xml with no model involved
#
# That last group is the reason the extraction runner must call a pass even
# when no LLM is configured: the figures are already in the file, and reporting
# them as missing would be a lie about a document sitting right there.
OFFLINE_FACTS = frozenset({
    "doc.types_present",
    "doc.extensions",
    "case.postcheck_date",
    "doc.financials.report_year",
    "doc.financials.total_assets",
    "doc.financials.total_capital",
    "doc.financials.revenue_prior_year",
    "doc.financials.revenue_current_year",
    "doc.financials.net_profit_current_year",
})

CASES = ("case_demo", "case_thieu_ho_so")


def main() -> int:
    from src.config import Config
    from src.pipeline import run_postcheck
    from src.rules.registry import RULES

    needs = {rule.id: set(rule.needs) for rule in RULES}
    problems: list[str] = []
    summaries: list[str] = []

    for case in CASES:
        result = run_postcheck(
            case_dir=ROOT / "samples" / case,
            config=Config(),                 # no LLM, no executor
            tax_code="0201123795",
            approval_date="2025-01-02",
            postcheck_date="2026-09-15",
        )

        for finding in result.findings:
            if finding.status in ("PASS", "FAIL"):
                unavailable = needs[finding.rule_id] - OFFLINE_FACTS
                if unavailable:
                    problems.append(
                        f"{case}/{finding.rule_id}: graded {finding.status} although it "
                        f"needs {sorted(unavailable)}, which no offline source fills"
                    )
            elif not finding.missing:
                problems.append(
                    f"{case}/{finding.rule_id}: insufficient data but names nothing missing"
                )

        if sum(result.extraction_calls.values()):
            problems.append(f"{case}: called an LLM despite none being configured")
        if "Thiếu dữ liệu" not in result.report_markdown:
            problems.append(f"{case}: the report does not mention the missing-data state")

        counts = result.counts
        summaries.append(
            f"{case}: {counts['PASS']} pass, {counts['FAIL']} fail, "
            f"{counts['INSUFFICIENT_DATA']} insufficient"
        )

    return report(problems, "; ".join(summaries))


if __name__ == "__main__":
    sys.exit(main())
