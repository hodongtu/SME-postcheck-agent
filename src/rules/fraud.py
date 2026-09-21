"""BRD 2.2 - Identify signs of suspected fraud.

BRD row 20 - checking a document's authenticity against the fraud-risk team's
guidance - is deliberately NOT implemented: that guidance was never supplied, and
the business has confirmed the row is out of scope. Only row 19, the
internal-consistency check, is graded here.

The functions here DECIDE; they do not declare. Which of them is a rule, under
what id, title and severity, and on which facts, is in src/rules/registry.py -
one catalogue for all of them, so there is one place to look.
"""

from src.facts import Facts
from src.rules._compare import distinct, make_address_normalizer, norm_digits, norm_text, rows
from src.rules.engine import Verdict, failed, passed


def check_internal_consistency(facts: Facts, settings: dict) -> Verdict:
    """The same field must read the same on every document in the dossier.

    Distinct from V01-V06, which compare against LOS: a dossier can match LOS
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
    unread: list[str] = []
    checked = 0
    for label, path, normalizer in fields:
        pairs = rows(facts.get(path)) if facts.has(path) else []
        if not pairs:
            unread.append(label)
            continue
        checked += 1
        groups = distinct(pairs, normalizer)
        if len(groups) > 1:
            detail = " | ".join(
                f"“{as_printed}” ({', '.join(files)})"
                for as_printed, files in groups.values()
            )
            conflicts.append(f"{label}: {detail}")

    missing_note = (
        f"; không chứng từ nào đọc được: {', '.join(unread)}" if unread else ""
    )
    if not checked:
        return failed("Không chứng từ nào đọc được thông tin định danh để đối chiếu chéo")
    if conflicts:
        return failed(
            f"Bất nhất ở {len(conflicts)}/{checked} trường được đối chiếu — "
            + "; ".join(conflicts) + missing_note
        )
    return passed(
        f"{checked}/{checked} trường định danh nhất quán xuyên suốt các chứng từ"
        + missing_note
    )
