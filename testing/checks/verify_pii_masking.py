"""Nothing personal leaves the machine, and every figure still does.

Measured on the payload the model actually receives, not on the masking function
in isolation: a fake LLM records what it is handed at each of the three places
this system talks to a model.

The PII below is DECLARED, not discovered. A check that asked the detector which
strings are personal would agree with itself no matter how much it missed.
"""

from _harness import ROOT, report
import sys

# One synthetic document carrying both halves of the problem: names, a national
# ID, a phone number and an email that must never be sent, and figures that must
# arrive untouched. The digits below are the trap - masking any 9-12 digit run
# takes the tax code and the balance sheet with it.
DOCUMENT_TEXT = """
CÔNG TY CỔ PHẦN XÂY DỰNG - THƯƠNG MẠI KIM HẢI
Mã số thuế: 0201123795
Người đại diện theo pháp luật: Nguyễn Văn A
Số CCCD: 001080001234 — Năm sinh: 1980
Điện thoại: 0912345678 — Email: ketoan@kimhai.com.vn
Kế toán trưởng  Lê Thị Kế Toán   Giám đốc  Nguyễn Văn A

BẢNG CÂN ĐỐI KẾ TOÁN
TỔNG CỘNG TÀI SẢN                     50226331878
TỔNG CỘNG NGUỒN VỐN                   50226331878
Doanh thu bán hàng và cung cấp dịch vụ 62116063780
Lợi nhuận sau thuế                       382284650
"""

PII_PLAINTEXT = (
    "Nguyễn Văn A",
    "Lê Thị Kế Toán",
    "001080001234",
    "0912345678",
    "ketoan@kimhai.com.vn",
)

# Not PII, and a report built on masked figures would be worthless.
MUST_SURVIVE = ("0201123795", "50226331878", "62116063780", "382284650", "1980")

# The same name as OCR misreads it. Both must hash the same or every comparison
# against LOS fails and looks like a dossier that disagrees with itself.
OCR_VARIANTS = ("Trần Thị Mai Hương", "Trần Thị Mai Hưỡng")


class Recorder:
    """Records every payload, answers with a fixed result."""

    def __init__(self, answer: str):
        self.answer = answer
        self.seen: list[str] = []

    def __call__(self, value):
        self.seen.append(str(getattr(value, "messages", value)))
        return self.answer


def capturing_llm(answer: str):
    """A Runnable that stands where the real client stands in `prompt | llm | parser`."""

    from langchain_core.runnables import RunnableLambda

    recorder = Recorder(answer)
    return RunnableLambda(recorder), recorder


def run_passes(mask_pii: bool, answer: str):
    """One extraction pass over the document above. Returns (llm, document)."""

    from src.config import Config
    from src.passes import run_extraction_passes
    from src.settings import get_settings
    from src.types import PostcheckDocument
    from src.utils.pii import vault_from_settings

    llm, recorder = capturing_llm(answer)
    document = PostcheckDocument(
        path=str(ROOT / "samples" / "case_demo" / "ho_so_tai_chinh" / "bctc.xlsx"),
        filename="bang_can_doi_ke_toan_2025.xlsx",
        content=DOCUMENT_TEXT,
        document_type="bang_can_doi_ke_toan",
    )
    settings = get_settings()
    vault = vault_from_settings(settings) if mask_pii else None
    run_extraction_passes([document], Config(financial_statement_llm=llm),
                          settings, vault)
    return recorder, document, vault


def main() -> int:
    import json
    import sqlite3

    from src.report.commentary import build_commentary
    from src.rules.engine import Finding
    from src.settings import get_settings
    from src.utils.pii import (
        DIGEST_PATTERN,
        IDENTIFIER,
        pii_hash,
        vault_from_settings,
    )

    problems: list[str] = []
    from src.agents.extraction.financial_statement_extraction import (
        REQUIRED_TOP_LEVEL_KEYS,
    )
    # The name is echoed back inside the answer the way a real extraction echoes
    # what it read, so assertion 5 measures the round trip and not a constant.
    answer = json.dumps({
        **{key: {} for key in REQUIRED_TOP_LEVEL_KEYS},
        "document_type": "bang_can_doi_ke_toan",
        "audit_opinion": "Được lập bởi Nguyễn Văn A",
    })

    # 1 - nothing personal in what the model was handed.
    llm, document, vault = run_passes(mask_pii=True, answer=answer)
    if not llm.seen:
        problems.append("the extraction pass never called the model, so nothing was measured")
    payload = " ".join(llm.seen)
    for secret in PII_PLAINTEXT:
        if secret in payload:
            problems.append(f"PII reached the model in plaintext: {secret!r}")

    # 2 - and every figure did.
    for figure in MUST_SURVIVE:
        if figure not in payload:
            problems.append(
                f"{figure} was masked or dropped; a figure the report needs never "
                f"reached the model"
            )

    # 3 - the hash is the database key, so masking does not break the lookup.
    database = ROOT / "samples" / "dummy_db" / "postcheck_dummy.sqlite"
    if not database.exists():
        problems.append("samples/dummy_db/postcheck_dummy.sqlite is missing; "
                        "run make_dummy_db.py")
    else:
        with sqlite3.connect(database) as connection:
            stored = connection.execute(
                "SELECT cccd_cdn, ten_cdn FROM v_los_phe_duyet WHERE mst = ?",
                ("0201123795",),
            ).fetchone()
        if stored != (pii_hash("001080001234", IDENTIFIER), pii_hash("Nguyễn Văn A")):
            problems.append(
                "the hash of the ID and the name read from the document does not "
                "equal what the database stores, so a masked run cannot query it"
            )

    # 4 - OCR spelling does not change the hash.
    first, second = (pii_hash(name) for name in OCR_VARIANTS)
    if first != second:
        problems.append(
            f"{OCR_VARIANTS[0]} and {OCR_VARIANTS[1]} hash differently, so the same "
            f"person reads as two people"
        )

    # 5 - the way back: tokens in the model's answer become names again.
    if document.financial_statement is None:
        problems.append(f"extraction returned nothing: {document.financial_statement_error}")
    elif "Nguyễn Văn A" not in str(document.financial_statement.get("audit_opinion")):
        problems.append(
            "the model's answer was not unmasked: "
            f"{document.financial_statement.get('audit_opinion')!r}"
        )

    # 6 - the commentary path, which sends conclusions rather than documents.
    # F01 is what section 1.2 of the template places, and the cross-document
    # consistency it reports is exactly where a person's name appears in prose.
    findings = [Finding(
        rule_id="F01", title="Thông tin định danh nhất quán giữa các chứng từ",
        expected="", observed="Tên chủ doanh nghiệp: “Nguyễn Văn A”, CCCD 001080001234",
        status="FAIL", severity="high", missing=(),
    )]
    commentary_llm, commentary_recorder = capturing_llm("Một. Hai. Ba. Bốn.")
    build_commentary(findings, commentary_llm, vault_from_settings(get_settings()),
                     sections=("1.2",))
    commentary_payload = " ".join(commentary_recorder.seen)
    if not commentary_recorder.seen:
        problems.append("the commentary pass never called the model")
    for secret in ("Nguyễn Văn A", "001080001234"):
        if secret in commentary_payload:
            problems.append(f"PII reached the commentary model in plaintext: {secret!r}")

    # 7 - and with masking off the PII really is there, or the assertions above
    # are measuring a path nothing travels.
    off, _, _ = run_passes(mask_pii=False, answer=answer)
    if "Nguyễn Văn A" not in " ".join(off.seen):
        problems.append(
            "with mask_pii off the name still did not reach the model, so "
            "assertion 1 proves nothing about masking"
        )

    # 8 - the report itself. LOS returns hashes for its PII columns, so any rule
    # that prints a name it read from LOS prints a 64-character digest instead -
    # unreadable to the reviewer, and personal data leaving in another direction.
    # C06 and E08 did exactly this until they were changed to count shareholders
    # rather than name them.
    from src.config import Config
    from src.pipeline import run_postcheck
    from src.tools._executor import sqlite_executor

    if database.exists():
        result = run_postcheck(
            case_dir=ROOT / "samples" / "case_demo",
            config=Config(query_executor=sqlite_executor(str(database))),
            tax_code="0201123795",
            approval_date="2026-04-01",
            postcheck_date="2026-09-15",
        )
        for finding in result.findings:
            for label, text in (("observed", finding.observed),
                                ("expected", finding.expected)):
                digest = DIGEST_PATTERN.search(str(text))
                if digest:
                    problems.append(
                        f"{finding.rule_id}.{label} prints a hash instead of a "
                        f"conclusion: {digest.group(0)[:16]}…"
                    )
        if DIGEST_PATTERN.search(result.report_markdown):
            problems.append("the rendered report contains a hash")

    return report(
        problems,
        f"{len(PII_PLAINTEXT)} personal values masked at the extraction and the "
        f"commentary call, {len(MUST_SURVIVE)} figures untouched, the document's "
        f"hashes equal the database's, two OCR spellings of one name agree, and "
        f"no conclusion in a full run prints a hash",
    )


if __name__ == "__main__":
    sys.exit(main())
