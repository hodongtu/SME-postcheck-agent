"""BRD 2.3.b - Do the criteria the business unit assessed meet the credit conditions. """

from src.facts import Facts
from src.rules.engine import Verdict, failed, passed


DEBT_GROUP_LIMITS: tuple[tuple[str, str, str], ...] = (
    ("KH", "cic.customer_debt_group_at_approval", "max_cic_group"),
    ("CDN", "cic.owner_debt_group_at_approval", "BO_max_cic_group"),
)


def program_criteria(facts: Facts, settings: dict) -> dict:
    program = settings.get("programs", {}).get(str(facts.get("los.program")), {})
    return program.get("criteria", {})


def debt_group_thresholds(facts: Facts, settings: dict) -> dict[str, int] | None:
    """The program's two debt-group ceilings, or None if LOS names no known program."""

    criteria = program_criteria(facts, settings)
    if not criteria:
        return None
    return {key: int(criteria[key]) for _, _, key in DEBT_GROUP_LIMITS}


def is_off_focus_industry(facts: Facts, settings: dict) -> bool:
    """True when the customer's industry is NOT one the bank focuses on. """

    focus = {str(code) for code in settings.get("focus_GSO", [])}
    return str(facts.get("los.gso_code")) not in focus


def is_restricted_industry(facts: Facts, settings: dict) -> bool:
    """True when the customer's industry is one credit is restricted for. """

    restricted = {str(code) for code in settings.get("restricted_GSO", [])}
    return str(facts.get("los.gso_code")) in restricted


def check_restricted_industry(facts: Facts, settings: dict) -> Verdict:
    """An industry on the restricted list should not have been granted credit."""

    code = facts.get("los.gso_code")
    restricted = [str(item) for item in settings.get("restricted_GSO", [])]

    if not restricted:
        return passed(
            f"Danh mục ngành nghề hạn chế trong cấu hình hệ thống đang TRỐNG nên không có mã "
            f"nào để đối chiếu; mã GSO của khách hàng là {code}"
        )
    if is_restricted_industry(facts, settings):
        return failed(
            f"Ngành nghề mã GSO {code} thuộc danh mục hạn chế cấp tín dụng "
            f"({len(restricted)} mã trong danh mục)"
        )
    return passed(
        f"Ngành nghề mã GSO {code} không thuộc danh mục hạn chế cấp tín dụng"
    )


def unsecured_eligible(facts: Facts, settings: dict) -> tuple[bool, list[str]]:
    """Does the customer qualify for unsecured lending, and if not, why not. """

    reasons: list[str] = []

    if is_off_focus_industry(facts, settings):
        reasons.append(
            f"ngành nghề mã GSO {facts.get('los.gso_code')} không thuộc nhóm trọng tâm"
        )

    thresholds = debt_group_thresholds(facts, settings)
    if thresholds is None:
        reasons.append(
            f"chương trình {facts.get('los.program')} chưa khai trong cấu hình hệ "
            f"thống nên không đối chiếu được ngưỡng nhóm nợ"
        )
    else:
        for label, path, key in DEBT_GROUP_LIMITS:
            group = int(facts.get(path))
            if group > thresholds[key]:
                reasons.append(
                    f"{label} nhóm nợ {group}, vượt ngưỡng tín chấp {thresholds[key]}"
                )

    for label, path, what in (
        ("KH", "blwl.customer_at_approval", "BL/WL"),
        ("CDN", "blwl.owner_at_approval", "BL/WL"),
        ("KH", "amc.customer_at_approval", "luồng thu hồi nợ AMC"),
        ("CDN", "amc.owner_at_approval", "luồng thu hồi nợ AMC"),
    ):
        if facts.get(path):
            reasons.append(f"{label} nằm trong {what} tại thời điểm phê duyệt")

    return (not reasons), reasons


def check_industry_ccr(facts: Facts, settings: dict) -> Verdict:
    """An industry outside the focus list forces CCR to 100%."""

    ccr = float(facts.get("t24.ccr"))
    required = float(settings["unsecured_ccr_pct"])
    code = facts.get("los.gso_code")

    if not is_off_focus_industry(facts, settings):
        return passed(f"Ngành nghề mã GSO {code} thuộc nhóm trọng tâm; CCR hạch toán {ccr:g}%")
    if ccr != required:
        return failed(
            f"Ngành nghề mã GSO {code} không thuộc nhóm trọng tâm nên CCR phải bằng "
            f"{required:g}%, thực tế hạch toán {ccr:g}%"
        )
    return passed(
        f"Ngành nghề mã GSO {code} không thuộc nhóm trọng tâm và CCR đã hạch toán {ccr:g}%"
    )


SHAREHOLDER_PREFIX = "cổ đông "


def _subjects_on_list(
    facts: Facts, prefix: str, moment: str, *, shareholders: bool = True
) -> list[str]:
    """Which subjects are on one list at one moment. """

    listed: list[str] = []
    for label, path in (
        ("KH", f"{prefix}.customer_at_{moment}"),
        ("CDN", f"{prefix}.owner_at_{moment}"),
    ):
        if facts.get(path):
            listed.append(label)
    if shareholders:
        # Counted, NOT named: the name arrives hashed from LOS, and a report line
        # carrying the hash is neither readable nor allowed to leave.
        hits = sum(1 for present in
                   (facts.get(f"{prefix}.shareholders_at_{moment}") or {}).values()
                   if present)
        listed.extend([SHAREHOLDER_PREFIX] * hits)
    return listed


def check_amc(facts: Facts, settings: dict) -> Verdict:
    """Being in a recovery workflow fails this criterion outright. """

    listed = _subjects_on_list(facts, "amc", "approval", shareholders=False)
    if listed:
        return failed(
            f"{' và '.join(listed)} ở luồng thu hồi nợ AMC tại thời điểm phê duyệt"
        )
    return passed("KH và CDN đều không ở luồng thu hồi nợ AMC tại thời điểm phê duyệt")


def _shareholder_problems(
    facts: Facts, groups: dict, threshold: int, moment: str
) -> list[str]:
    """What is wrong with the shareholders, counted rather than named. """

    problems: list[str] = []
    over = sum(1 for group in groups.values()
               if group is not None and int(group) >= threshold)
    if over:
        problems.append(f"{over} cổ đông có nhóm nợ từ {threshold} trở lên")
    for prefix, what in (("blwl", "BL/WL"), ("amc", "luồng thu hồi nợ AMC")):
        listed = sum(1 for item in _subjects_on_list(facts, prefix, moment)
                     if item == SHAREHOLDER_PREFIX)
        if listed:
            problems.append(f"{listed} cổ đông nằm trong {what}")
    return problems


def check_shareholders(facts: Facts, settings: dict) -> Verdict:
    """The shareholders, across all three lookups at once. """

    groups = facts.get("cic.shareholder_debt_groups_at_approval") or {}
    threshold = int(settings["debt_group_warning_threshold"])
    problems = _shareholder_problems(facts, groups, threshold, "approval")
    unknown = sum(1 for group in groups.values() if group is None)

    if problems:
        return failed(
            f"Nhóm {len(groups)} cổ đông tại thời điểm phê duyệt có dấu hiệu: "
            + "; ".join(problems)
        )
    note = f"; {unknown} cổ đông không tra được nhóm nợ" if unknown else ""
    return passed(
        f"{len(groups)} cổ đông đều dưới nhóm nợ {threshold}, không ai trong BL/WL "
        f"hay luồng thu hồi nợ AMC{note}"
    )


def check_debt_group(facts: Facts, settings: dict) -> Verdict:
    """A debt group over the program's ceiling fails this criterion outright.

    No CCR escape: see check_amc.
    """

    program = facts.get("los.program")
    thresholds = debt_group_thresholds(facts, settings)
    if thresholds is None:
        return failed(
            f"Chương trình {program} chưa khai trong cấu hình hệ thống nên không "
            f"đối chiếu được nhóm nợ với ngưỡng tín chấp"
        )

    seen: list[str] = []
    over: list[str] = []
    for label, path, key in DEBT_GROUP_LIMITS:
        threshold = thresholds[key]
        group = int(facts.get(path))
        seen.append(f"{label} nhóm {group} (ngưỡng {threshold})")
        if group > int(threshold):
            over.append(f"{label} nhóm {group} vượt ngưỡng {threshold}")

    if over:
        return failed(f"{'; '.join(over)} của chương trình {program}")
    return passed(
        f"Nhóm nợ tại thời điểm phê duyệt: {', '.join(seen)} — trong ngưỡng của "
        f"chương trình {program}"
    )


def check_blwl(facts: Facts, settings: dict) -> Verdict:
    """Being on the black/warning list fails this criterion outright.

    A hit on either the company or its legal representative is a hit, and no CCR
    reading rescues it - see check_amc for why the CCR question lives in O03.
    """

    customer = bool(facts.get("blwl.customer_at_approval"))
    owner = bool(facts.get("blwl.owner_at_approval"))
    listed = [label for label, present in (("KH", customer), ("CDN", owner)) if present]

    if listed:
        return failed(f"{' và '.join(listed)} nằm trong BL/WL tại thời điểm phê duyệt")
    return passed("KH và CDN đều không nằm trong BL/WL tại thời điểm phê duyệt")
