"""BRD 2.3.b - Do the criteria the business unit assessed meet the credit conditions.

`unsecured_eligible` is the shared condition of this group and is reused by O03
(BRD 2.3.c): a customer who does not qualify for unsecured lending must be
booked at CCR 100%. Keeping it in one place is what stops the two groups from
drifting apart.

The functions here DECIDE; they do not declare. Which of them is a rule, under
what id, title and severity, and on which facts, is in src/rules/registry.py -
one catalogue for all of them, so there is one place to look.
"""

from __future__ import annotations

from src.facts import Facts
from src.rules.engine import Verdict, failed, passed


# Who is measured against which threshold. The business owner (BO, written CDN
# in the BRD's Vietnamese) carries a limit of their own.
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
    """True when the customer's industry is NOT one the bank focuses on.

    `focus_GSO` lists the industries in focus, so being absent from it is what
    carries the consequence. The list used to name the opposite - the off-focus
    industries - and reading it the old way would force CCR to 100% on exactly
    the customers the bank wants.
    """

    focus = {str(code) for code in settings.get("focus_GSO", [])}
    return str(facts.get("los.gso_code")) not in focus


def is_restricted_industry(facts: Facts, settings: dict) -> bool:
    """True when the customer's industry is one credit is restricted for.

    A separate list from `focus_GSO` because the consequence differs: off-focus
    means the facility must be booked at CCR 100%, restricted means it should not
    have been granted. Deliberately NOT part of `unsecured_eligible` - folding a
    refusal into an unsecured-lending test is how O03 would start saying that a
    restricted industry merely needs more collateral.
    """

    restricted = {str(code) for code in settings.get("restricted_GSO", [])}
    return str(facts.get("los.gso_code")) in restricted


def check_restricted_industry(facts: Facts, settings: dict) -> Verdict:
    """An industry on the restricted list should not have been granted credit."""

    code = facts.get("los.gso_code")
    restricted = [str(item) for item in settings.get("restricted_GSO", [])]

    if not restricted:
        return passed(
            f"Danh mục ngành nghề hạn chế trong config đang TRỐNG nên không có mã "
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
    """Does the customer qualify for unsecured lending, and if not, why not.

    Four conditions: an industry the bank focuses on, debt groups within the
    program's thresholds, no entry on the black or warning list, and no entry on
    the AMC recovery list - the first three from BRD 2.3.b, the fourth added by
    the business alongside them.

    The SHAREHOLDERS are checked too, but by C06, and their hits deliberately do
    not enter this function. A shareholder on a list is a risk signal about the
    company's ownership; whether it disqualifies the company from unsecured
    lending is a policy question nobody has answered, and answering it here by
    implication would silently make O03 stricter than the program says.

    The customer and the legal representative carry SEPARATE debt-group
    thresholds - `max_cic_group` and `BO_max_cic_group` - because a program may
    tolerate more from one than the other.

    Being on the black or warning list is unconditional: no program switches it
    off, so there is no flag to read.
    """

    reasons: list[str] = []

    if is_off_focus_industry(facts, settings):
        reasons.append(
            f"ngành nghề mã GSO {facts.get('los.gso_code')} không thuộc nhóm trọng tâm"
        )

    thresholds = debt_group_thresholds(facts, settings)
    if thresholds is None:
        reasons.append(
            f"chương trình {facts.get('los.program')} không có trong "
            f"config/programs.yaml nên không đối chiếu được ngưỡng nhóm nợ"
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
    """Which subjects are on one list at one moment.

    `shareholders=False` restricts it to the company and its representative. The
    two groups are separated by a flag rather than by slicing the result: a
    subject only appears when it is actually a hit, so there is no fixed position
    to slice at.
    """

    listed: list[str] = []
    for label, path in (
        ("KH", f"{prefix}.customer_at_{moment}"),
        ("CDN", f"{prefix}.owner_at_{moment}"),
    ):
        if facts.get(path):
            listed.append(label)
    if shareholders:
        for name, present in (facts.get(f"{prefix}.shareholders_at_{moment}") or {}).items():
            if present:
                listed.append(f"{SHAREHOLDER_PREFIX}{name}")
    return listed


def check_amc(facts: Facts, settings: dict) -> Verdict:
    """Being in a recovery workflow fails this criterion outright.

    A hit is a hit: no CCR reading rescues it. Whether the booking then carries
    the right CCR is a different question, asked by O03 through
    `unsecured_eligible` - which still reads this list.
    """

    listed = _subjects_on_list(facts, "amc", "approval", shareholders=False)
    if listed:
        return failed(
            f"{' và '.join(listed)} ở luồng thu hồi nợ AMC tại thời điểm phê duyệt"
        )
    return passed("KH và CDN đều không ở luồng thu hồi nợ AMC tại thời điểm phê duyệt")


def check_shareholders(facts: Facts, settings: dict) -> Verdict:
    """The shareholders, across all three lookups at once.

    One rule rather than three because the question the business asks is about
    the subject, not about the list: are the people behind this company clean.
    The cost is that a gap in any one lookup blocks the whole check - which is
    the honest outcome, since two lists out of three clears nobody.
    """

    groups = facts.get("cic.shareholder_debt_groups_at_approval") or {}
    threshold = int(settings["debt_group_warning_threshold"])
    stakes = {str(p.get("name") or ""): p.get("stake_pct")
              for p in facts.get("los.shareholders") or []}

    problems = [f"{name} nhóm nợ {group}" for name, group in groups.items()
                if group is not None and int(group) >= threshold]
    for prefix, what in (("blwl", "BL/WL"), ("amc", "luồng thu hồi nợ AMC")):
        for item in _subjects_on_list(facts, prefix, "approval"):
            if item.startswith(SHAREHOLDER_PREFIX):
                problems.append(f"{item} nằm trong {what}")
    unknown = [name for name, group in groups.items() if group is None]

    described = ", ".join(
        f"{name} {stakes.get(name)}%" if stakes.get(name) is not None else name
        for name in groups
    )
    if problems:
        return failed(
            f"{len(problems)} dấu hiệu trên nhóm cổ đông ({described}): "
            + "; ".join(problems)
        )
    note = f"; {len(unknown)} cổ đông không tra được nhóm nợ: {', '.join(unknown)}" if unknown else ""
    return passed(
        f"{len(groups)} cổ đông ({described}) đều dưới nhóm nợ {threshold}, "
        f"không ai trong BL/WL hay luồng thu hồi nợ AMC{note}"
    )


def check_debt_group(facts: Facts, settings: dict) -> Verdict:
    """A debt group over the program's ceiling fails this criterion outright.

    No CCR escape: see check_amc.
    """

    program = facts.get("los.program")
    thresholds = debt_group_thresholds(facts, settings)
    if thresholds is None:
        return failed(
            f"Chương trình {program} không có trong config/programs.yaml nên không "
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
