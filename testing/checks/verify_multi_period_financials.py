"""Statements from several periods merge correctly, and the filing outranks the scan.

A dossier can carry the 2025 statements as a scan and the 2024 ones as an e-tax
filing, or the same period in both formats at once. Two things must hold:

  - the reporting period is the latest period found ANYWHERE in the dossier,
    not the period of whichever file happened to sort first;
  - where one period exists in both formats, the figures taken are the filing's.

The second is not logic this project writes. FinancialRatioCalculator already
merges by (period, metric) and ranks by source, with SOURCE_RANK putting "xml"
above "llm". All the pipeline has to do is pass the source marker along - and
for a long time it passed an empty string, so an exact figure and a guessed one
were treated as equals.

Payloads are built here rather than extracted, so no LLM is called: the model
path cannot run offline, and the merge is what is under test.
"""

from _harness import report
import sys


CURRENT_YEAR = 2025
PRIOR_YEAR = 2024

FILING_TOTAL_ASSETS = 47_704_469_267         # what the e-tax filing says for 2024
FILING_NET_REVENUE = 71_176_996_993
SCANNED_TOTAL_ASSETS = 44_000_000_000        # what the scan claims for the same year
SCANNED_NET_REVENUE = 66_000_000_000
CURRENT_TOTAL_ASSETS = 50_226_331_878
CURRENT_NET_REVENUE = 62_116_063_780


def _statement_block(year: int, total_assets: int, net_revenue: int) -> dict:
    label = f"Năm {year}"
    return {
        "customer": {"name": "CÔNG TY MẪU", "tax_code": "0201123795"},
        "document_type": "BCTC",
        "reporting_period": {
            "period_label": label,
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
            "comparative_period_label": None,
        },
        "audit_opinion": {"is_audited": False, "opinion_type": "không xác định",
                          "auditor_name": None, "notes": "", "page": None},
        "balance_sheet": {
            "unit": "VNĐ", "source_unit": "dong", "page": None, "years": [label],
            "item_columns": ["label", "code", label, "page"],
            "line_items": [
                ["TỔNG CỘNG TÀI SẢN", "270", total_assets, None],
                ["TỔNG CỘNG NGUỒN VỐN", "440", total_assets, None],
            ],
        },
        "income_statement": {
            "unit": "VNĐ", "source_unit": "dong", "page": None, "years": [label],
            "item_columns": ["label", "code", label, "page"],
            "line_items": [["Doanh thu thuần", "10", net_revenue, None]],
        },
        "cash_flow_statement": {
            "unit": "VNĐ", "source_unit": "dong", "page": None, "years": [],
            "item_columns": [], "line_items": [],
        },
        "extraction_notes": [],
    }


def main() -> int:
    from src.agents.extraction.financial_statement_extraction import (
        EXTRACTION_SOURCE_LLM,
        EXTRACTION_SOURCE_XML,
        conform_financial_statement,
    )
    from src.facts import Facts
    from src.settings import get_settings
    from src.pipeline import _assemble_financials
    from src.types import PostcheckDocument

    def _document(filename: str, payload: dict, source: str) -> PostcheckDocument:
        document = PostcheckDocument(path=f"/samples/{filename}", filename=filename)
        document.document_type = "bao_cao_tai_chinh"
        document.financial_statement = conform_financial_statement(payload, source)
        return document

    # Named so that the scanned prior-year file sorts FIRST. Under the old
    # behaviour the period came from statements[0], which is exactly this file.
    documents = [
        _document("a_ban_scan_2024.xlsx",
                  _statement_block(PRIOR_YEAR, SCANNED_TOTAL_ASSETS, SCANNED_NET_REVENUE),
                  EXTRACTION_SOURCE_LLM),
        _document("b_filing_2024.xml",
                  _statement_block(PRIOR_YEAR, FILING_TOTAL_ASSETS, FILING_NET_REVENUE),
                  EXTRACTION_SOURCE_XML),
        _document("c_ban_scan_2025.xlsx",
                  _statement_block(CURRENT_YEAR, CURRENT_TOTAL_ASSETS, CURRENT_NET_REVENUE),
                  EXTRACTION_SOURCE_LLM),
    ]

    facts = Facts()
    _assemble_financials(facts, documents, get_settings())
    problems: list[str] = []

    report_year = facts.get("doc.financials.report_year")
    if report_year != CURRENT_YEAR:
        problems.append(
            f"report_year is {report_year!r}, expected {CURRENT_YEAR} - the latest "
            f"period in the dossier, not the period of the first file"
        )

    current_assets = facts.get("doc.financials.total_assets")
    if current_assets != CURRENT_TOTAL_ASSETS:
        problems.append(
            f"total_assets is {current_assets!r}, expected {CURRENT_TOTAL_ASSETS} "
            f"from the {CURRENT_YEAR} statements"
        )

    prior_revenue = facts.get("doc.financials.revenue_prior_year")
    if prior_revenue == SCANNED_NET_REVENUE:
        problems.append(
            f"revenue_prior_year took the scan's figure ({SCANNED_NET_REVENUE:,}) for "
            f"{PRIOR_YEAR}; the e-tax filing for the same period says "
            f"{FILING_NET_REVENUE:,} and must win"
        )
    elif prior_revenue != FILING_NET_REVENUE:
        problems.append(
            f"revenue_prior_year is {prior_revenue!r}, expected the filing's "
            f"{FILING_NET_REVENUE}"
        )

    # A dossier with one period only must say so rather than invent a prior year.
    single = Facts()
    _assemble_financials(single, [documents[2]], get_settings())
    if single.has("doc.financials.revenue_prior_year"):
        problems.append(
            "a single-period dossier reported a prior-year revenue it cannot have"
        )
    elif "một kỳ" not in single.reason("doc.financials.revenue_prior_year"):
        problems.append(
            "a single-period dossier does not explain why the prior year is missing: "
            + single.reason("doc.financials.revenue_prior_year")
        )

    return report(
        problems,
        f"report year {CURRENT_YEAR} taken from the latest period in the dossier; "
        f"for {PRIOR_YEAR} the e-tax filing outranked the scan",
    )


if __name__ == "__main__":
    sys.exit(main())
