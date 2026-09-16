"""BRD 2.2 - Identify signs of suspected fraud."""

from __future__ import annotations

from collections import Counter

from src.facts import Facts
from src.rules._compare import distinct, make_address_normalizer, norm_digits, norm_text, rows
from src.rules.engine import Rule, Verdict, as_date, failed, passed


def _check_internal_consistency(facts: Facts, settings: dict) -> Verdict:
    """The same field must read the same on every document in the dossier.

    Distinct from V01-V06, which compare against BEP: a dossier can match BEP
    on one document and contradict itself on another.
    """

    address = make_address_normalizer(settings.get("address_abbreviations", {}))
    fields = [
        ("Mã số thuế", "doc.tax_code_values", norm_digits),
        ("Tên khách hàng", "doc.customer_name_values", norm_text),
        ("Địa chỉ", "doc.address_values", address),
        ("Tên chủ doanh nghiệp", "doc.owner_name_values", norm_text),
    ]

    conflicts: list[str] = []
    checked = 0
    for label, path, normalizer in fields:
        pairs = rows(facts.get(path))
        if not pairs:
            continue
        checked += 1
        groups = distinct(pairs, normalizer)
        if len(groups) > 1:
            detail = " | ".join(
                f"“{as_printed}” ({', '.join(files)})"
                for as_printed, files in groups.values()
            )
            conflicts.append(f"{label}: {detail}")

    if not checked:
        return failed("Không chứng từ nào đọc được thông tin định danh để đối chiếu chéo")
    if conflicts:
        return failed(
            f"Bất nhất ở {len(conflicts)}/{checked} trường được đối chiếu — "
            + "; ".join(conflicts)
        )
    return passed(f"{checked}/{checked} trường định danh nhất quán xuyên suốt các chứng từ")


def _check_authenticity(facts: Facts, settings: dict) -> Verdict:
    """The machine-checkable part of the fraud team's guidance.

    Two signals a machine can assert on its own: a document dated after the
    approval, and one document number reused across files. The rest - signs of
    alteration, an odd typeface, a copied seal - is expert judgement and is
    raised in the commentary section rather than concluded here.
    """

    approval_date = as_date(facts.get("bep.batch_valid_from"))
    signals: list[str] = []

    dated_after: list[str] = []
    for filename, value in rows(facts.get("doc.document_date_values")):
        try:
            document_date = as_date(value)
        except ValueError:
            continue
        if document_date > approval_date:
            dated_after.append(f"{filename} ({document_date.isoformat()})")
    if dated_after:
        signals.append(
            f"{len(dated_after)} chứng từ đề ngày sau ngày phê duyệt "
            f"{approval_date.isoformat()}: " + ", ".join(dated_after)
        )

    numbers = rows(facts.get("doc.document_number_values"))
    counts = Counter(norm_text(value) for _, value in numbers)
    reused = [value for value, seen in counts.items() if value and seen > 1]
    if reused:
        detail = "; ".join(
            f"“{value}”: "
            + ", ".join(name for name, raw in numbers if norm_text(raw) == value)
            for value in reused
        )
        signals.append(f"{len(reused)} số hiệu bị dùng lại ở nhiều chứng từ — {detail}")

    if signals:
        return failed("; ".join(signals))
    return passed(
        f"Không thấy dấu hiệu máy kiểm được trên {len(numbers)} chứng từ: không chứng "
        f"từ nào đề ngày sau ngày phê duyệt, không số hiệu nào bị trùng"
    )


# Answers BRD rows 18 and 19 (section 2.2).
RULES: tuple[Rule, ...] = (
    Rule("F01", "Thông tin khách hàng nhất quán xuyên suốt các chứng từ",
         "MST, tên KH, địa chỉ và tên CDN chỉ có một giá trị trên toàn hồ sơ", "high",
         ("doc.tax_code_values", "doc.customer_name_values",
          "doc.address_values", "doc.owner_name_values"), _check_internal_consistency),
    Rule("F02", "Tính xác thực của chứng từ theo hướng dẫn QTRR gian lận",
         "Không chứng từ nào đề ngày sau ngày phê duyệt; không số hiệu nào bị dùng lại",
         "high",
         ("doc.document_date_values", "doc.document_number_values",
          "bep.batch_valid_from"), _check_authenticity),
)
