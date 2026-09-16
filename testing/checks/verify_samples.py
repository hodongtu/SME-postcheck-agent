"""The sample dossiers still exercise what they were built to exercise.

Every bug found while building them would have been caught here:

  - a CIC report left unidentified because three types share the keyword
    "thong tin cic", so the R20 pass never ran;
  - a .jpg dropped before the rules saw it, so the format rule passed on a
    dossier holding a photo instead of a document;
  - a CSV that crashed the reader on a sniffed delimiter csv.reader refuses.

It also holds the one scanned document in the suite. src/utils/reading/ocr.py is
593 lines that nothing else ever runs: without a PDF carrying no text layer, the
whole OCR path could break and every check would still pass.

case_demo is the complete dossier and case_thieu_ho_so the deficient one. A
suite that only ever sees a good dossier proves very little, which is why both
exist and why this check asserts the bad one is genuinely bad.
"""

from _harness import ROOT, report
import sys
from pathlib import Path


TAX_CODE = "0201123795"


SAMPLES = ROOT / "samples"
DEMO = "case_demo"
MULTI_PERIOD = "case_nhieu_ky_bctc"
DEFICIENT = "case_thieu_ho_so"


def main() -> int:
    from src.agents.extraction.financial_statement_extraction import (
        extract_financial_statement_from_xml,
    )
    from src.agents.calculator.financial_ratio_calculator import FinancialRatioCalculator
    from src.config import Config
    from src.passes import EXTRACTION_PASSES
    from src.pipeline import read_case_documents
    from src.settings import get_settings

    settings = get_settings()
    problems: list[str] = []
    config = Config()

    for name in (DEMO, MULTI_PERIOD, DEFICIENT):
        if not (SAMPLES / name).is_dir():
            problems.append(f"samples/{name} is missing - run samples/make_samples.py")
    if problems:
        return report(problems, "")

    demo = read_case_documents(SAMPLES / DEMO, config)
    multi_period = read_case_documents(SAMPLES / MULTI_PERIOD, config)
    deficient = read_case_documents(SAMPLES / DEFICIENT, config)

    # --- case_demo: every pass has something to work on --------------------
    matched = {
        extraction_pass.label
        for document in demo if document.document_type
        for extraction_pass in EXTRACTION_PASSES
        if extraction_pass.applies_to(document.document_type)
    }
    unexercised = {p.label for p in EXTRACTION_PASSES} - matched
    if unexercised:
        problems.append(
            f"{DEMO} has no document for {sorted(unexercised)} - those passes are "
            f"never exercised by a sample"
        )

    # --- case_demo: the full B1CP checklist, in permitted formats ----------
    present = {document.document_type for document in demo if document.document_type}
    required = {item["type_id"] for item in settings["programs"]["B1CP"]["checklist"]
                if item["requirement"] == "mandatory"}
    if required - present:
        problems.append(f"{DEMO} is missing mandatory B1CP items: {sorted(required - present)}")

    allowed = {extension.lower() for extension in settings["allowed_extensions"]}
    for document in demo:
        if document.extension not in allowed:
            problems.append(f"{DEMO}/{document.filename}: format is not permitted")
        if not document.document_type:
            problems.append(
                f"{DEMO}/{document.filename}: not identified "
                f"({document.document_type_note or 'no reason recorded'})"
            )

    # --- the e-tax XML: real figures with no LLM ---------------------------
    statements = [d for d in demo if d.extension == ".xml"]
    if not statements:
        problems.append(f"{DEMO} has no e-tax XML - the no-LLM path is untested")
    for document in statements:
        payload, error = extract_financial_statement_from_xml(document.path)
        if payload is None:
            problems.append(f"{DEMO}/{document.filename}: parse_tax_xml failed - {error}")
            continue
        metrics = FinancialRatioCalculator().extract_yearly_metrics(
            [{"financial_statement_extraction": payload,
              "financial_statement_extraction_source": ""}]
        )
        balanced = [
            year for year, values in metrics.items()
            if values.get("total_assets") is not None
            and values.get("total_assets") == values.get("total_capital")
        ]
        if not balanced:
            problems.append(
                f"{DEMO}/{document.filename}: no year where total assets equal total "
                f"capital - rule P06 gets nothing from the XML path"
            )

    # --- case_thieu_ho_so: genuinely deficient -----------------------------
    deficient_present = {d.document_type for d in deficient if d.document_type}
    if not required - deficient_present:
        problems.append(f"{DEFICIENT} has every mandatory item - it is not deficient")
    if all(d.extension in allowed for d in deficient):
        problems.append(
            f"{DEFICIENT} has no format violation - rule P03 is never exercised"
        )
    if not any(d.extraction_status == "unsupported" for d in deficient):
        problems.append(
            f"{DEFICIENT} has no unreadable file - the case where a photo stands in "
            f"for a document is never exercised"
        )

    # The XML must reach the rules through the pipeline, not only when
    # parse_tax_xml is called by hand. The runner used to skip every pass when
    # no LLM was configured, so these figures never arrived.
    from src.facts import Facts
    from src.passes import run_extraction_passes
    from src.pipeline import assemble_document_facts

    run_extraction_passes(demo, config)
    facts = Facts()
    assemble_document_facts(facts, demo, settings)
    from_xml = (
        "doc.financials.report_year",
        "doc.financials.total_assets",
        "doc.financials.total_capital",
        "doc.financials.revenue_prior_year",
        "doc.financials.revenue_current_year",
    )
    absent = [path for path in from_xml if not facts.has(path)]
    if absent:
        problems.append(
            f"{DEMO}: the e-tax XML did not reach the rules with no LLM configured - "
            f"{absent} are missing"
        )
    if facts.get("doc.financials.total_assets") != facts.get("doc.financials.total_capital"):
        problems.append(f"{DEMO}: the XML figures do not balance, so P06 cannot pass offline")

    # --- the multi-period dossier: two years, one of them in two formats ---
    if len(multi_period) < 3:
        problems.append(f"{MULTI_PERIOD} has only {len(multi_period)} files, expected 3")
    for document in multi_period:
        if document.document_type != "bao_cao_tai_chinh":
            problems.append(
                f"{MULTI_PERIOD}/{document.filename}: identified as "
                f"'{document.document_type or '—'}', expected bao_cao_tai_chinh"
            )
    formats = {document.extension for document in multi_period}
    if ".xml" not in formats or formats <= {".xml"}:
        problems.append(
            f"{MULTI_PERIOD} must carry BOTH an e-tax XML and a scanned-style file, "
            f"found {sorted(formats)} - otherwise the precedence rule is untested"
        )

    # --- the scanned document: the only thing that runs OCR ----------------
    scans = [d for d in demo if d.extension == ".pdf"]
    if not scans:
        problems.append(
            f"{DEMO} has no PDF - the OCR path is never exercised by any check"
        )
    for document in scans:
        raw = Path(document.path).read_bytes()
        if b"/Font" in raw:
            problems.append(
                f"{DEMO}/{document.filename} carries a text layer, so it is read "
                f"without OCR - a scan is the point"
            )
        if document.extraction_status != "success" or not document.content.strip():
            problems.append(
                f"{DEMO}/{document.filename}: OCR produced nothing "
                f"({document.extraction_error or 'no error recorded'}). "
                f"Tesseract may be missing: brew install tesseract tesseract-lang"
            )
            continue
        # Diacritics and a tax code are what OCR gets wrong first, so assert on
        # those rather than on a character count.
        for probe in (TAX_CODE, "Nợ đủ tiêu chuẩn"):
            if probe not in document.content:
                problems.append(
                    f"{DEMO}/{document.filename}: OCR did not read back {probe!r}"
                )

    unreadable = sum(1 for d in demo if d.extraction_status == "failed")
    note = f" ({unreadable} .docx unread - pip install python-docx)" if unreadable else ""
    return report(
        problems,
        f"{DEMO}: {len(demo)} files, all identified, all 5 passes exercised, "
        f"{len(scans)} scan read back through OCR, "
        f"{len(from_xml)} financial facts read from the e-tax XML with no LLM{note}; "
        f"{MULTI_PERIOD}: {len(multi_period)} statements across two periods; "
        f"{DEFICIENT}: {len(deficient)} files, deficient as intended",
    )


if __name__ == "__main__":
    sys.exit(main())
