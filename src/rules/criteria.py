"""BRD 2.3.b - Do the criteria the business unit assessed meet the credit conditions.

`unsecured_eligible` is the shared condition of this group and is reused by O03
(BRD 2.3.c): a customer who does not qualify for unsecured lending must be
booked at CCR 100%. Keeping it in one place is what stops the two groups from
drifting apart.
"""

from __future__ import annotations

from src.facts import Facts
from src.rules.engine import Rule, Verdict, failed, passed


def program_criteria(facts: Facts, settings: dict) -> dict:
    program = settings.get("programs", {}).get(str(facts.get("bep.program")), {})
    return program.get("criteria", {})


def is_non_core_industry(facts: Facts, settings: dict) -> bool:
    codes = {str(code) for code in settings.get("non_core_industries", [])}
    return str(facts.get("bep.gso_code")) in codes


def unsecured_eligible(facts: Facts, settings: dict) -> tuple[bool, list[str]]:
    """Does the customer qualify for unsecured lending, and if not, why not.

    Three conditions, one per line of BRD 2.3.b: a core industry, a debt group
    within the program's threshold, and no entry on the black/warning list.
    """

    criteria = program_criteria(facts, settings)
    reasons: list[str] = []

    if is_non_core_industry(facts, settings):
        reasons.append(f"ngành nghề mã GSO {facts.get('bep.gso_code')} không trọng tâm")

    threshold = criteria.get("max_cic_group_unsecured")
    if threshold is not None:
        for label, path in (
            ("KH", "cic.customer_debt_group_at_approval"),
            ("CDN", "cic.owner_debt_group_at_approval"),
        ):
            group = int(facts.get(path))
            if group > int(threshold):
                reasons.append(f"{label} nhóm nợ {group}, vượt ngưỡng tín chấp {threshold}")

    if criteria.get("blwl_blocks_unsecured"):
        for label, path in (
            ("KH", "blwl.customer_at_approval"),
            ("CDN", "blwl.owner_at_approval"),
        ):
            if facts.get(path):
                reasons.append(f"{label} nằm trong BL/WL tại thời điểm phê duyệt")

    return (not reasons), reasons


def _check_industry_ccr(facts: Facts, settings: dict) -> Verdict:
    """A restricted or non-core industry forces CCR to 100%."""

    ccr = float(facts.get("t24.ccr"))
    required = float(settings["unsecured_ccr_pct"])
    code = facts.get("bep.gso_code")

    if not is_non_core_industry(facts, settings):
        return passed(f"Ngành nghề mã GSO {code} thuộc nhóm trọng tâm; CCR hạch toán {ccr:g}%")
    if ccr != required:
        return failed(
            f"Ngành nghề mã GSO {code} không trọng tâm nên CCR phải bằng {required:g}%, "
            f"thực tế hạch toán {ccr:g}%"
        )
    return passed(f"Ngành nghề mã GSO {code} không trọng tâm và CCR đã hạch toán {ccr:g}%")


def _check_debt_group(facts: Facts, settings: dict) -> Verdict:
    """A customer or owner with bad debt: do they still meet the unsecured criteria."""

    criteria = program_criteria(facts, settings)
    threshold = criteria.get("max_cic_group_unsecured")
    program = facts.get("bep.program")
    if threshold is None:
        return failed(
            f"Chương trình {program} chưa khai max_cic_group_unsecured trong "
            f"config/programs.yaml nên không đối chiếu được nhóm nợ với tiêu chí"
        )

    customer = int(facts.get("cic.customer_debt_group_at_approval"))
    owner = int(facts.get("cic.owner_debt_group_at_approval"))
    ccr = float(facts.get("t24.ccr"))
    over = [f"{label} nhóm {group}" for label, group in (("KH", customer), ("CDN", owner))
            if group > int(threshold)]

    if not over:
        return passed(
            f"Nhóm nợ tại thời điểm phê duyệt: KH nhóm {customer}, CDN nhóm {owner}, "
            f"trong ngưỡng tín chấp {threshold} của chương trình {program}"
        )
    if ccr < float(settings["unsecured_ccr_pct"]):
        return failed(
            f"{', '.join(over)} vượt ngưỡng tín chấp {threshold} của chương trình "
            f"{program}, nhưng khoản vay vẫn hạch toán CCR {ccr:g}%"
        )
    return passed(
        f"{', '.join(over)} vượt ngưỡng tín chấp {threshold}, và khoản vay đã hạch toán "
        f"CCR {ccr:g}% nên không hưởng tiêu chí tín chấp"
    )


def _check_blwl(facts: Facts, settings: dict) -> Verdict:
    """A customer or owner on the black/warning list: do they meet the criteria."""

    criteria = program_criteria(facts, settings)
    customer = bool(facts.get("blwl.customer_at_approval"))
    owner = bool(facts.get("blwl.owner_at_approval"))
    ccr = float(facts.get("t24.ccr"))
    listed = [label for label, present in (("KH", customer), ("CDN", owner)) if present]

    if not listed:
        return passed("KH và CDN đều không nằm trong BL/WL tại thời điểm phê duyệt")
    if not criteria.get("blwl_blocks_unsecured"):
        return passed(
            f"{' và '.join(listed)} nằm trong BL/WL, nhưng chương trình "
            f"{facts.get('bep.program')} không lấy BL/WL làm điều kiện chặn tín chấp"
        )
    if ccr < float(settings["unsecured_ccr_pct"]):
        return failed(
            f"{' và '.join(listed)} nằm trong BL/WL tại thời điểm phê duyệt nên không "
            f"đáp ứng tiêu chí tín chấp, nhưng khoản vay hạch toán CCR {ccr:g}%"
        )
    return passed(
        f"{' và '.join(listed)} nằm trong BL/WL, và khoản vay đã hạch toán CCR {ccr:g}%"
    )


# Answers BRD rows 30, 31, 32 (section 2.3, lending criteria group).
RULES: tuple[Rule, ...] = (
    Rule("C01", "Ngành nghề hạn chế/không trọng tâm thì CCR bằng 100%",
         "Ngành nghề không trọng tâm buộc CCR = 100%", "high",
         ("bep.gso_code", "t24.ccr"), _check_industry_ccr),
    Rule("C02", "Nợ xấu, nợ cần chú ý của KH/CDN so với tiêu chí chương trình",
         "Nhóm nợ vượt ngưỡng tín chấp thì khoản vay không được hưởng tín chấp", "high",
         ("bep.program", "cic.customer_debt_group_at_approval",
          "cic.owner_debt_group_at_approval", "t24.ccr"), _check_debt_group),
    Rule("C03", "KH/CDN nằm trong BL/WL so với tiêu chí chương trình",
         "Có tên trong BL/WL thì khoản vay không được hưởng tín chấp", "high",
         ("bep.program", "blwl.customer_at_approval", "blwl.owner_at_approval",
          "t24.ccr"), _check_blwl),
)
