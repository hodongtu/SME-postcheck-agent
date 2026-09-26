"""BRD 2.1 - Verify the customer information. """

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
from src.rules.engine import Verdict, failed, passed, variance_pct
from src.utils.common import normalize_text
from src.utils.pii import IDENTIFIER, NAME, as_hash, show


def _against_los(
    facts: Facts,
    los_path: str,
    doc_path: str,
    label: str,
    normalizer: Callable[[Any], str],
) -> Verdict:
    """Compare one LOS field against the same field on every document read."""

    expected = facts.get(los_path)
    normalized_expected = normalizer(expected)
    pairs = rows(facts.get(doc_path))

    if not pairs:
        return failed(
            f"{label} trên LOS là “{show(expected)}” nhưng không chứng từ nào đọc được "
            f"{label.lower()} để đối chiếu"
        )

    mismatched = [(name, value) for name, value in pairs
                  if normalizer(value) != normalized_expected]
    if mismatched:
        detail = "; ".join(f"{name}: “{show(value)}”" for name, value in mismatched)
        return failed(
            f"{label} trên LOS là “{show(expected)}”; lệch ở {len(mismatched)}/{len(pairs)} "
            f"chứng từ — {detail}"
        )
    return passed(
        f"{label} “{show(expected)}” khớp trên toàn bộ {len(pairs)} chứng từ đọc được"
    )


def _hashed(kind: str):
    """Compare by hash - LOS returns hashes for the columns that hold PII."""

    return lambda value: as_hash(value, kind)


def check_customer_name(facts: Facts, settings: dict) -> Verdict:
    return _against_los(facts, "los.customer_name", "doc.customer_name_values",
                        "Tên khách hàng", norm_text)


def check_tax_code(facts: Facts, settings: dict) -> Verdict:
    return _against_los(facts, "los.tax_code", "doc.tax_code_values",
                        "Mã số thuế", norm_digits)


def check_address(facts: Facts, settings: dict) -> Verdict:
    normalizer = make_address_normalizer(settings.get("address_abbreviations", {}))
    return _against_los(facts, "los.address", "doc.address_values",
                        "Địa chỉ", normalizer)


def check_owner_name(facts: Facts, settings: dict) -> Verdict:
    return _against_los(facts, "los.owner_name", "doc.owner_name_values",
                        "Tên chủ doanh nghiệp", _hashed(NAME))


def check_owner_id_number(facts: Facts, settings: dict) -> Verdict:
    return _against_los(facts, "los.owner_id_number", "doc.owner_id_number_values",
                        "Số CCCD chủ doanh nghiệp", _hashed(IDENTIFIER))


def check_owner_birth_year(facts: Facts, settings: dict) -> Verdict:
    return _against_los(facts, "los.owner_birth_year", "doc.owner_birth_year_values",
                        "Năm sinh chủ doanh nghiệp", norm_year)


def check_industry(facts: Facts, settings: dict) -> Verdict:
    """LOS, the business registration and the site visit must describe one business."""

    on_los = facts.get("los.industry")
    on_registration = facts.get("doc.industry_on_registration")
    on_sitevisit = facts.get("doc.industry_on_sitevisit")

    differences: list[str] = []
    if not industry_matches(on_los, on_registration):
        differences.append(f"ĐKKD ghi “{on_registration}”")
    if not industry_matches(on_los, on_sitevisit):
        differences.append(f"khảo sát thực địa ghi “{on_sitevisit}”")

    if differences:
        return failed(f"Ngành nghề trên LOS là “{on_los}”; " + ", ".join(differences))
    return passed(
        f"Ngành nghề “{on_los}” nhất quán giữa LOS, ĐKKD và khảo sát thực địa "
        f"(mã GSO {facts.get('los.gso_code')})"
    )


def check_sitevisit_online(facts: Facts, settings: dict) -> Verdict:
    """The industry as the RM keyed it in, against the file and the report filed."""

    keyed = facts.get("los.sitevisit_online.industry")
    on_file = facts.get("los.industry")
    filed = facts.get("doc.industry_on_sitevisit")

    differences = []
    if not industry_matches(keyed, on_file):
        differences.append(f"hồ sơ LOS ghi “{on_file}”")
    if not industry_matches(keyed, filed):
        differences.append(f"báo cáo khảo sát ghi “{filed}”")

    if differences:
        return failed(
            f"Ngành nghề RM nhập khi khảo sát là “{keyed}”; " + ", ".join(differences)
        )
    return passed(
        f"Ngành nghề “{keyed}” nhất quán giữa khảo sát RM nhập, hồ sơ LOS và báo cáo "
        f"khảo sát nộp kèm"
    )


def check_financials_online(facts: Facts, settings: dict) -> Verdict:
    """The RM keyed in the SAME statements that were filed - period and kind. """

    keyed_year = str(facts.get("los.financials_online.report_year"))
    filed_year = str(facts.get("doc.financials.report_year"))
    keyed_type = facts.get("los.financials_online.report_type")
    filed_type = facts.get("doc.financials.report_type")

    differences = []
    if keyed_year != filed_year:
        differences.append(
            f"kỳ báo cáo — RM nhập năm {keyed_year}, hồ sơ nộp năm {filed_year}"
        )
    if norm_text(keyed_type) != norm_text(filed_type):
        differences.append(
            f"loại báo cáo — RM nhập “{keyed_type}”, hồ sơ nộp “{filed_type}”"
        )

    if differences:
        return failed(
            "BCTC RM nhập không cùng một báo cáo với hồ sơ: " + "; ".join(differences)
        )
    return passed(f"BCTC RM nhập và hồ sơ nộp cùng là “{filed_type}” kỳ {filed_year}")


def check_persona_photos(facts: Facts, settings: dict) -> Verdict:
    """Do the site-visit photos show what this customer's persona should show. """

    if not facts.get("los.is_site_visit"):
        return passed(
            "LOS không yêu cầu khảo sát thực địa với hồ sơ này nên không cần đối "
            "chiếu ảnh"
        )

    persona = str(facts.get("los.persona"))
    table = {normalize_text(name): entry
             for name, entry in (settings.get("persona_evidence") or {}).items()}
    entry = table.get(normalize_text(persona))
    if entry is None:
        return failed(
            f"Chân dung “{persona}” chưa khai dấu hiệu kỳ vọng trong cấu hình hệ "
            f"thống nên không biết ảnh cần cho thấy gì"
        )

    expected = {normalize_text(marker) for marker in entry["expected"]}
    minimum = int(entry["min_markers"])

    photos = facts.get("doc.sitevisit_photo_evidence")
    seen: dict[str, list[str]] = {}
    for photo in photos:
        for marker in photo.get("markers") or []:
            if normalize_text(marker) in expected:
                seen.setdefault(normalize_text(marker), []).append(
                    str(photo.get("filename", "?"))
                )

    detail = "; ".join(
        f"{marker} ({', '.join(sorted(set(files)))})" for marker, files in sorted(seen.items())
    )
    if len(seen) < minimum:
        return failed(
            f"Chân dung “{persona}” cần ít nhất {minimum} dấu hiệu trong "
            f"{len(expected)} dấu hiệu kỳ vọng, {len(photos)} ảnh chỉ cho thấy "
            f"{len(seen)}" + (f": {detail}" if detail else " — không dấu hiệu nào")
        )
    return passed(
        f"Chân dung “{persona}”: {len(photos)} ảnh cho thấy {len(seen)}/{minimum} "
        f"dấu hiệu kỳ vọng — {detail}"
    )
