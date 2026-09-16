"""A financial statement has one shape, whichever file it came from.

A dossier may carry the statements as a scanned PDF, as an e-tax XML, or both.
The rules downstream must not care: the same keys, the same statement blocks,
the same column layout. Where the two paths differ, they differ in what a rule
reads, and that is how V01, V02 and F01 quietly lost the tax filing as a source
of the customer's name.

Neither path costs anything here. The XML is parsed for real from the sample
dossier; the model path is exercised by pushing a schema-shaped dict through
the same conforming step, so the contract is tested without a single call.
"""

from _harness import ROOT, report
import sys


XML_SAMPLE = ROOT / "samples" / "case_demo" / "ho_so_tai_chinh" / "bao_cao_tai_chinh_2025.xml"

# The shape the extraction prompt asks the model for, trimmed to one line per
# statement. Written out rather than recorded from a run so that a change to the
# prompt's schema shows up here as a decision instead of a surprise.
LLM_SHAPED_RESULT = {
    "customer": {"ten": "CÔNG TY MẪU", "ma_so_thue": "0101234567"},
    "document_type": "BCTC riêng lẻ",
    "reporting_period": {
        "period_label": "Năm 2025",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "comparative_period_label": "Năm 2024",
    },
    "audit_opinion": {
        "is_audited": False,
        "opinion_type": "không xác định",
        "auditor_name": None,
        "notes": "",
        "page": None,
    },
    "balance_sheet": {
        "unit": "VNĐ", "source_unit": "dong", "page": 3,
        "years": ["Năm 2025", "Năm 2024"],
        "item_columns": ["label", "code", "Năm 2025", "Năm 2024", "page"],
        "line_items": [["TỔNG CỘNG TÀI SẢN", "270", 50226331878, 47704469267, 3]],
    },
    "income_statement": {
        "unit": "VNĐ", "source_unit": "dong", "page": 5,
        "years": ["Năm 2025", "Năm 2024"],
        "item_columns": ["label", "code", "Năm 2025", "Năm 2024", "page"],
        "line_items": [["Doanh thu thuần", "10", 62116063780, 71176996993, 5]],
    },
    "cash_flow_statement": {
        "unit": "VNĐ", "source_unit": "dong", "page": 7,
        "years": ["Năm 2025", "Năm 2024"],
        "item_columns": ["label", "code", "Năm 2025", "Năm 2024", "page"],
        "line_items": [["Lưu chuyển tiền thuần trong kỳ", "50", 1000, 2000, 7]],
    },
    "extraction_notes": [],
}

STATEMENT_BLOCKS = ("balance_sheet", "income_statement", "cash_flow_statement")


def main() -> int:
    import copy

    from src.agents.extraction import financial_statement_extraction as module

    problems: list[str] = []

    conform = getattr(module, "conform_financial_statement", None)
    if conform is None:
        return report(
            ["financial_statement_extraction has no conform_financial_statement() - "
             "the two paths have no shared definition of their output shape"],
            "",
        )

    from_xml, error = module.extract_financial_statement_from_xml(str(XML_SAMPLE))
    if from_xml is None:
        return report([f"the XML sample did not parse: {error}"], "")
    from_llm = conform(copy.deepcopy(LLM_SHAPED_RESULT), module.EXTRACTION_SOURCE_LLM)

    # --- the same keys, at the top and inside every statement --------------
    if set(from_xml) != set(from_llm):
        only_xml = sorted(set(from_xml) - set(from_llm))
        only_llm = sorted(set(from_llm) - set(from_xml))
        problems.append(
            f"top-level keys differ - only in XML: {only_xml}; only in LLM: {only_llm}"
        )
    for key in module.REQUIRED_TOP_LEVEL_KEYS:
        for name, payload in (("XML", from_xml), ("LLM", from_llm)):
            if key not in payload:
                problems.append(f"{name} path is missing the required key '{key}'")

    for block in STATEMENT_BLOCKS:
        xml_block, llm_block = from_xml.get(block), from_llm.get(block)
        if not isinstance(xml_block, dict) or not isinstance(llm_block, dict):
            problems.append(f"'{block}' is not a block on both paths")
            continue
        if set(xml_block) != set(llm_block):
            problems.append(
                f"'{block}' keys differ - XML {sorted(xml_block)} vs LLM {sorted(llm_block)}"
            )
        for name, block_payload in (("XML", xml_block), ("LLM", llm_block)):
            columns = block_payload.get("item_columns") or []
            if columns[:2] != ["label", "code"] or columns[-1:] != ["page"]:
                problems.append(
                    f"{name}/{block}: item_columns is {columns}, expected "
                    f"['label', 'code', <one per period>, 'page']"
                )

    # --- what a rule actually reads ----------------------------------------
    for name, payload in (("XML", from_xml), ("LLM", from_llm)):
        customer = payload.get("customer")
        if not isinstance(customer, dict) or set(customer) < {"ten", "ma_so_thue"}:
            problems.append(
                f"{name} path has no usable 'customer' block - V01, V02 and F01 lose "
                f"this document as a source of the name and tax code"
            )

    if from_xml.get("extraction_source") != module.EXTRACTION_SOURCE_XML:
        problems.append(
            f"XML path marks its source as {from_xml.get('extraction_source')!r}; "
            f"without {module.EXTRACTION_SOURCE_XML!r} the calculator cannot rank an "
            f"exact figure above a scanned one"
        )
    if from_llm.get("extraction_source") != module.EXTRACTION_SOURCE_LLM:
        problems.append(
            f"model path marks its source as {from_llm.get('extraction_source')!r}, "
            f"expected {module.EXTRACTION_SOURCE_LLM!r}"
        )

    # --- the one difference that is deliberate -----------------------------
    # The e-tax form is B01a-DNN (TT133), whose indicator codes are a different
    # scheme from the TT200 codes FinancialRatioCalculator matches on: total
    # assets is 200 there and 270 here. Filling the code slot from the XML would
    # make seventeen metrics match on the wrong scheme, so it stays empty and the
    # alias matcher does the work. This asserts it stays that way.
    xml_codes = {row[1] for row in from_xml["balance_sheet"]["line_items"]}
    if xml_codes != {None}:
        problems.append(
            f"XML balance sheet now carries statement codes {sorted(c for c in xml_codes if c)} - "
            f"those are TT133 codes and the metric matcher expects TT200; see the note "
            f"in this check"
        )

    return report(
        problems,
        f"both paths return {len(set(from_xml))} top-level keys, the same three "
        f"statement blocks and the same column layout; sources marked "
        f"{from_xml.get('extraction_source')!r} and {from_llm.get('extraction_source')!r}",
    )


if __name__ == "__main__":
    sys.exit(main())
