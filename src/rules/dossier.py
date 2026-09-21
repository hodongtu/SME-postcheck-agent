"""BRD 2.3.a - Do the documents satisfy the required checklist.

The functions here DECIDE; they do not declare. Which of them is a rule, under
what id, title and severity, and on which facts, is in src/rules/registry.py -
one catalogue for all of them, so there is one place to look.
"""

from datetime import date

from src.agents.documents.document_matrix import get_type
from src.facts import Facts
from src.rules.engine import Verdict, as_date, failed, passed


def _program(facts: Facts, settings: dict) -> dict:
    """The configuration of the program this customer belongs to."""

    return settings.get("programs", {}).get(str(facts.get("los.program")), {})


def _label(type_id: str) -> str:
    document_type = get_type(type_id)
    return document_type.short_label if document_type else type_id


def check_program(facts: Facts, settings: dict) -> Verdict:
    """Identify the credit program from the tax code / customer id."""

    program = str(facts.get("los.program"))
    known = sorted(settings.get("programs", {}))
    if program not in known:
        return failed(
            f"LOS trả ra chương trình “{program}”, không nằm trong danh mục đã khai "
            f"({', '.join(known)}) nên không xác định được checklist và bộ tiêu chí"
        )
    return passed(f"Khách hàng thuộc chương trình {program} (MST {facts.get('los.tax_code')})")


def check_checklist(facts: Facts, settings: dict) -> Verdict:
    """Every mandatory item of the program's checklist is present, matched by filename."""

    program = _program(facts, settings)
    checklist = program.get("checklist", [])
    if not checklist:
        return failed(
            f"Chương trình {facts.get('los.program')} chưa khai checklist trong "
            f"config/programs.yaml nên không đối chiếu được danh mục hồ sơ"
        )

    present = {str(type_id) for type_id in facts.get("doc.types_present")}
    required = [
        item for item in checklist
        if item.get("requirement") == "mandatory"
        and (item.get("when") != "site_visit" or facts.get("los.is_site_visit"))
    ]
    absent = [item["type_id"] for item in required if item["type_id"] not in present]

    if absent:
        return failed(
            f"Thiếu {len(absent)}/{len(required)} đầu mục bắt buộc của chương trình "
            f"{facts.get('los.program')}: " + ", ".join(_label(t) for t in absent)
        )
    return passed(
        f"Đủ {len(required)}/{len(required)} đầu mục bắt buộc của chương trình "
        f"{facts.get('los.program')}"
    )


def check_file_formats(facts: Facts, settings: dict) -> Verdict:
    """File formats allowed by the regulation: Word / Excel / PDF / XML."""

    allowed = {extension.lower() for extension in settings.get("allowed_extensions", [])}
    files = facts.get("doc.extensions")
    rejected = [f"{row['filename']} ({row['extension']})" for row in files
                if str(row.get("extension", "")).lower() not in allowed]

    if rejected:
        return failed(
            f"{len(rejected)}/{len(files)} file sai định dạng (cho phép "
            f"{', '.join(sorted(allowed))}): " + ", ".join(rejected)
        )
    return passed(f"{len(files)}/{len(files)} file đúng định dạng cho phép")


def check_signature_and_seal(facts: Facts, settings: dict) -> Verdict:
    """Customer-supplied documents carry both a signature and a company seal."""

    program = _program(facts, settings)
    must_be_signed = {item["type_id"] for item in program.get("checklist", [])
                      if item.get("requires_signature")}
    documents = [row for row in facts.get("doc.signature_and_seal")
                 if str(row.get("type_id")) in must_be_signed]

    if not documents:
        return failed(
            "Không chứng từ nào trong hồ sơ thuộc nhóm bắt buộc có chữ ký và con dấu, "
            "nên không có gì để kiểm — kiểm tra lại bước nhận diện tài liệu"
        )

    incomplete: list[str] = []
    for row in documents:
        absent = [name for name, present in
                  (("chữ ký", row.get("has_signature")), ("con dấu", row.get("has_seal")))
                  if not present]
        if absent:
            incomplete.append(f"{row.get('filename')} (thiếu {' và '.join(absent)})")

    if incomplete:
        return failed(
            f"{len(incomplete)}/{len(documents)} chứng từ chưa đủ chữ ký/con dấu: "
            + ", ".join(incomplete)
        )
    return passed(
        f"{len(documents)}/{len(documents)} chứng từ bắt buộc đều có đủ chữ ký và con dấu"
    )


def check_digital_signature(facts: Facts, settings: dict) -> Verdict:
    """The financial statements carry a digital signature."""

    if not facts.get("doc.financials.has_digital_signature"):
        return failed("BCTC khách hàng cung cấp không có chữ ký điện tử")
    return passed("BCTC có chữ ký điện tử")


def check_balance(facts: Facts, settings: dict) -> Verdict:
    """Total assets equal total capital."""

    total_assets = float(facts.get("doc.financials.total_assets"))
    total_capital = float(facts.get("doc.financials.total_capital"))
    difference = total_assets - total_capital

    if abs(difference) > float(settings.get("balance_tolerance_vnd", 0)):
        return failed(
            f"BCTC không cân đối: tổng tài sản {total_assets:,.0f} đ, tổng nguồn vốn "
            f"{total_capital:,.0f} đ, lệch {difference:,.0f} đ"
        )
    return passed(f"BCTC cân đối: tổng tài sản = tổng nguồn vốn = {total_assets:,.0f} đ")


def check_report_period(facts: Facts, settings: dict) -> Verdict:
    """The statements cover the period the regulation requires.

    A limit booked before 30 April must use the year N-2 statements; from
    30 April onwards, N-1.
    """

    booking_date = as_date(facts.get("t24.booking_date"))
    report_year = int(facts.get("doc.financials.report_year"))

    month, day = (int(part) for part in str(settings["financials_cutoff_mmdd"]).split("-"))
    cutoff = date(booking_date.year, month, day)
    before_cutoff = booking_date < cutoff
    required_year = booking_date.year - (2 if before_cutoff else 1)
    cutoff_label = f"{day:02d}/{month:02d}"

    if report_year != required_year:
        return failed(
            f"HMTD active ngày {booking_date.isoformat()} "
            f"({'trước' if before_cutoff else 'từ'} {cutoff_label}) nên phải dùng BCTC "
            f"năm {required_year}; hồ sơ nộp BCTC năm {report_year}"
        )
    return passed(
        f"HMTD active ngày {booking_date.isoformat()} và hồ sơ dùng BCTC năm "
        f"{report_year}, đúng quy định"
    )
