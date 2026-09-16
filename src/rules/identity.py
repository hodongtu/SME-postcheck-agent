"""BRD 2.1 - Verify the customer information.

Compare what head office returned (BEP) against the customer's documents and
the business unit's site visit.
"""

from __future__ import annotations

from typing import Any, Callable

from src.facts import Facts
from src.rules._compare import (
    industry_matches,
    make_address_normalizer,
    norm_digits,
    norm_text,
    norm_year,
    rows,
)
from src.rules.engine import Rule, Verdict, failed, passed


def _against_bep(
    facts: Facts,
    bep_path: str,
    doc_path: str,
    label: str,
    normalizer: Callable[[Any], str],
) -> Verdict:
    """Compare one BEP field against the same field on every document read."""

    expected = facts.get(bep_path)
    normalized_expected = normalizer(expected)
    pairs = rows(facts.get(doc_path))

    if not pairs:
        # The fact is present but every cell is blank: there is nothing to
        # compare, and passing quietly here is exactly the green-on-empty bug.
        return failed(
            f"{label} trên BEP là “{expected}” nhưng không chứng từ nào đọc được "
            f"{label.lower()} để đối chiếu"
        )

    mismatched = [(name, value) for name, value in pairs
                  if normalizer(value) != normalized_expected]
    if mismatched:
        detail = "; ".join(f"{name}: “{value}”" for name, value in mismatched)
        return failed(
            f"{label} trên BEP là “{expected}”; lệch ở {len(mismatched)}/{len(pairs)} "
            f"chứng từ — {detail}"
        )
    return passed(
        f"{label} “{expected}” khớp trên toàn bộ {len(pairs)} chứng từ đọc được"
    )


def _check_customer_name(facts: Facts, settings: dict) -> Verdict:
    return _against_bep(facts, "bep.customer_name", "doc.customer_name_values",
                        "Tên khách hàng", norm_text)


def _check_tax_code(facts: Facts, settings: dict) -> Verdict:
    return _against_bep(facts, "bep.tax_code", "doc.tax_code_values",
                        "Mã số thuế", norm_digits)


def _check_address(facts: Facts, settings: dict) -> Verdict:
    normalizer = make_address_normalizer(settings.get("address_abbreviations", {}))
    return _against_bep(facts, "bep.address", "doc.address_values",
                        "Địa chỉ", normalizer)


def _check_owner_name(facts: Facts, settings: dict) -> Verdict:
    return _against_bep(facts, "bep.owner_name", "doc.owner_name_values",
                        "Tên chủ doanh nghiệp", norm_text)


def _check_owner_id_number(facts: Facts, settings: dict) -> Verdict:
    return _against_bep(facts, "bep.owner_id_number", "doc.owner_id_number_values",
                        "Số CCCD chủ doanh nghiệp", norm_digits)


def _check_owner_birth_year(facts: Facts, settings: dict) -> Verdict:
    return _against_bep(facts, "bep.owner_birth_year", "doc.owner_birth_year_values",
                        "Năm sinh chủ doanh nghiệp", norm_year)


def _check_industry(facts: Facts, settings: dict) -> Verdict:
    """BEP, the business registration and the site visit must describe one business."""

    on_bep = facts.get("bep.industry")
    on_registration = facts.get("doc.industry_on_registration")
    on_sitevisit = facts.get("doc.industry_on_sitevisit")

    differences: list[str] = []
    if not industry_matches(on_bep, on_registration):
        differences.append(f"ĐKKD ghi “{on_registration}”")
    if not industry_matches(on_bep, on_sitevisit):
        differences.append(f"khảo sát thực địa ghi “{on_sitevisit}”")

    if differences:
        return failed(f"Ngành nghề trên BEP là “{on_bep}”; " + ", ".join(differences))
    return passed(
        f"Ngành nghề “{on_bep}” nhất quán giữa BEP, ĐKKD và khảo sát thực địa "
        f"(mã GSO {facts.get('bep.gso_code')})"
    )


# Answers BRD row 13 (section 2.1) - one row, seven identity fields.
RULES: tuple[Rule, ...] = (
    Rule("V01", "Tên khách hàng khớp giữa BEP và chứng từ",
         "Tên KH trên mọi chứng từ trùng với tên trên BEP", "high",
         ("bep.customer_name", "doc.customer_name_values"), _check_customer_name),
    Rule("V02", "Mã số thuế khớp giữa BEP và chứng từ",
         "MST trên mọi chứng từ trùng với MST trên BEP", "high",
         ("bep.tax_code", "doc.tax_code_values"), _check_tax_code),
    Rule("V03", "Địa chỉ khớp giữa BEP và chứng từ",
         "Địa chỉ trên mọi chứng từ trùng với địa chỉ trên BEP", "medium",
         ("bep.address", "doc.address_values"), _check_address),
    Rule("V04", "Tên chủ doanh nghiệp khớp giữa BEP và chứng từ",
         "Tên CDN trên mọi chứng từ trùng với tên trên BEP", "high",
         ("bep.owner_name", "doc.owner_name_values"), _check_owner_name),
    Rule("V05", "Số CCCD chủ doanh nghiệp khớp giữa BEP và chứng từ",
         "CCCD trên mọi chứng từ trùng với CCCD trên BEP", "high",
         ("bep.owner_id_number", "doc.owner_id_number_values"), _check_owner_id_number),
    Rule("V06", "Năm sinh chủ doanh nghiệp khớp giữa BEP và chứng từ",
         "Năm sinh CDN trên mọi chứng từ trùng với năm sinh trên BEP", "medium",
         ("bep.owner_birth_year", "doc.owner_birth_year_values"), _check_owner_birth_year),
    Rule("V07", "Ngành nghề khớp giữa BEP, ĐKKD và khảo sát thực địa",
         "Ngành nghề trên ba nguồn cùng mô tả một hoạt động", "medium",
         ("bep.industry", "bep.gso_code", "doc.industry_on_registration",
          "doc.industry_on_sitevisit"), _check_industry),
)
