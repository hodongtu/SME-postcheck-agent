"""BRD 2.3.a - Do the documents satisfy the required checklist."""

from __future__ import annotations

from datetime import date

from src.agents.documents.document_matrix import get_type
from src.facts import Facts
from src.rules.engine import Rule, Verdict, as_date, failed, passed


def _program(facts: Facts, settings: dict) -> dict:
    """The configuration of the program this customer belongs to."""

    return settings.get("programs", {}).get(str(facts.get("bep.program")), {})


def _label(type_id: str) -> str:
    document_type = get_type(type_id)
    return document_type.short_label if document_type else type_id


def _check_program(facts: Facts, settings: dict) -> Verdict:
    """Identify the credit program from the tax code / customer id."""

    program = str(facts.get("bep.program"))
    known = sorted(settings.get("programs", {}))
    if program not in known:
        return failed(
            f"BEP trả ra chương trình “{program}”, không nằm trong danh mục đã khai "
            f"({', '.join(known)}) nên không xác định được checklist và bộ tiêu chí"
        )
    return passed(f"Khách hàng thuộc chương trình {program} (MST {facts.get('bep.tax_code')})")


def _check_checklist(facts: Facts, settings: dict) -> Verdict:
    """Every mandatory item of the program's checklist is present, matched by filename."""

    program = _program(facts, settings)
    checklist = program.get("checklist", [])
    if not checklist:
        return failed(
            f"Chương trình {facts.get('bep.program')} chưa khai checklist trong "
            f"config/programs.yaml nên không đối chiếu được danh mục hồ sơ"
        )

    present = {str(type_id) for type_id in facts.get("doc.types_present")}
    required = [item for item in checklist if item.get("requirement") == "mandatory"]
    absent = [item["type_id"] for item in required if item["type_id"] not in present]

    if absent:
        return failed(
            f"Thiếu {len(absent)}/{len(required)} đầu mục bắt buộc của chương trình "
            f"{facts.get('bep.program')}: " + ", ".join(_label(t) for t in absent)
        )
    return passed(
        f"Đủ {len(required)}/{len(required)} đầu mục bắt buộc của chương trình "
        f"{facts.get('bep.program')}"
    )


def _check_file_formats(facts: Facts, settings: dict) -> Verdict:
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


def _check_signature_and_seal(facts: Facts, settings: dict) -> Verdict:
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


def _check_digital_signature(facts: Facts, settings: dict) -> Verdict:
    """The financial statements carry a digital signature."""

    if not facts.get("doc.financials.has_digital_signature"):
        return failed("BCTC khách hàng cung cấp không có chữ ký điện tử")
    return passed("BCTC có chữ ký điện tử")


def _check_balance(facts: Facts, settings: dict) -> Verdict:
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


def _check_report_period(facts: Facts, settings: dict) -> Verdict:
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


# Answers BRD rows 22, 24, 25, 26, 27 (section 2.3, document checklist group).
RULES: tuple[Rule, ...] = (
    Rule("P01", "Xác định được chương trình cấp tín dụng của khách hàng",
         "Chương trình BEP trả ra nằm trong danh mục đã khai (B1CP/MISA/PL++)", "high",
         ("bep.program", "bep.tax_code"), _check_program),
    Rule("P02", "Đủ hồ sơ theo checklist của chương trình",
         "Mọi đầu mục bắt buộc của chương trình đều có mặt trong hồ sơ", "high",
         ("bep.program", "doc.types_present"), _check_checklist),
    Rule("P03", "Định dạng file phù hợp theo quy định",
         "Mọi file thuộc định dạng Word/Excel/PDF/XML", "low",
         ("doc.extensions",), _check_file_formats),
    Rule("P04", "Chứng từ khách hàng cung cấp đủ chữ ký và con dấu",
         "Mọi chứng từ thuộc nhóm bắt buộc đều có cả chữ ký và con dấu", "high",
         ("bep.program", "doc.signature_and_seal"), _check_signature_and_seal),
    Rule("P05", "BCTC có chữ ký điện tử",
         "BCTC khách hàng cung cấp mang chữ ký điện tử", "medium",
         ("doc.financials.has_digital_signature",), _check_digital_signature),
    Rule("P06", "BCTC cân đối: tổng tài sản bằng tổng nguồn vốn",
         "Tổng tài sản = tổng nguồn vốn", "high",
         ("doc.financials.total_assets", "doc.financials.total_capital"), _check_balance),
    Rule("P07", "Kỳ BCTC phù hợp theo quy định",
         "Active trước 30/4 dùng BCTC N-2; từ 30/4 dùng BCTC N-1", "medium",
         ("doc.financials.report_year", "t24.booking_date"), _check_report_period),
)
