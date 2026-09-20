"""BRD 2.3.c - Did the business unit follow the credit process.

O05 and O06 are not in the BRD. They compare the credit application against
the systems, which the proposal extraction pass makes available at no extra
cost, and both differences are operational signals worth seeing. Their titles
say so.

The functions here DECIDE; they do not declare. Which of them is a rule, under
what id, title and severity, and on which facts, is in src/rules/registry.py -
one catalogue for all of them, so there is one place to look.
"""

from __future__ import annotations

from src.facts import Facts
from src.rules._compare import norm_text
from src.rules.criteria import unsecured_eligible
from src.rules.engine import Verdict, as_date, failed, passed, variance_pct


def check_within_validity(facts: Facts, settings: dict) -> Verdict:
    """The limit was booked while the approval was valid - BOTH ends of the window.

    BRD row 35 asks whether the booking happened while the approval was still in
    force, which is an interval. Booking before the batch took effect is as wrong
    as booking after it expired, and only the late half used to be checked.
    """

    booked = as_date(facts.get("t24.booking_date"))
    valid_from = as_date(facts.get("los.batch_valid_from"))
    valid_to = as_date(facts.get("los.batch_valid_to"))
    window = f"{valid_from.isoformat()} — {valid_to.isoformat()}"

    if booked < valid_from:
        early = (valid_from - booked).days
        return failed(
            f"HMTD hạch toán trên T24 ngày {booked.isoformat()}, trước ngày lô phê duyệt "
            f"có hiệu lực {valid_from.isoformat()} — sớm {early} ngày"
        )
    if booked > valid_to:
        late = (booked - valid_to).days
        return failed(
            f"HMTD hạch toán trên T24 ngày {booked.isoformat()}, sau ngày lô phê duyệt "
            f"hết hiệu lực {valid_to.isoformat()} — trễ {late} ngày"
        )
    return passed(
        f"HMTD hạch toán ngày {booked.isoformat()}, trong hiệu lực phê duyệt {window}"
    )


def check_limit_not_exceeded(facts: Facts, settings: dict) -> Verdict:
    """Booked limits do not exceed what head office approved, per product too."""

    active_total = float(facts.get("t24.active_limit"))
    approved_total = float(facts.get("los.approved_limit"))
    active_by_product = facts.get("t24.active_limit_by_product")
    approved_by_product = facts.get("los.approved_limit_by_product")

    exceeded: list[str] = []
    if active_total > approved_total:
        exceeded.append(
            f"tổng: active {active_total:,.0f} đ > phê duyệt {approved_total:,.0f} đ"
        )
    for product, amount in active_by_product.items():
        approved = float(approved_by_product.get(product, 0))
        if float(amount) > approved:
            exceeded.append(
                f"{product}: active {float(amount):,.0f} đ > phê duyệt {approved:,.0f} đ"
            )

    if exceeded:
        return failed("HMTD vượt giá trị hội sở trả ra — " + "; ".join(exceeded))
    return passed(
        f"Tổng HMTD active {active_total:,.0f} đ trong hạn mức phê duyệt "
        f"{approved_total:,.0f} đ; {len(active_by_product)}/{len(active_by_product)} "
        f"sản phẩm đều trong hạn mức"
    )


def check_ccr_booking(facts: Facts, settings: dict) -> Verdict:
    """Was CCR booked correctly: no unsecured eligibility means CCR must be 100%."""

    ccr = float(facts.get("t24.ccr"))
    required = float(settings["unsecured_ccr_pct"])
    eligible, reasons = unsecured_eligible(facts, settings)

    if eligible:
        return passed(
            f"KH đáp ứng tiêu chí tín chấp của chương trình {facts.get('los.program')}; "
            f"CCR hạch toán {ccr:g}% không bị ràng buộc mức {required:g}%"
        )
    if ccr != required:
        return failed(
            f"KH không đáp ứng tiêu chí tín chấp ({'; '.join(reasons)}) nên CCR phải bằng "
            f"{required:g}%, thực tế BBC hạch toán {ccr:g}%"
        )
    return passed(
        f"KH không đáp ứng tiêu chí tín chấp ({'; '.join(reasons)}) và BBC đã hạch toán "
        f"CCR {required:g}%"
    )


def check_collateral_structure(facts: Facts, settings: dict) -> Verdict:
    """CCR below 100% requires collateral to be a vehicle or real estate."""

    ccr = float(facts.get("t24.ccr"))
    threshold = float(settings["unsecured_ccr_pct"])
    allowed = {str(kind).upper() for kind in settings.get("secured_collateral_types", [])}
    items = facts.get("collateral.items")

    if ccr >= threshold:
        return passed(
            f"CCR {ccr:g}% không dưới {threshold:g}% nên không ràng buộc cấu trúc TSBĐ "
            f"({len(items)} tài sản ghi nhận)"
        )

    rejected = [f"{item.get('kind')} ({float(item.get('value') or 0):,.0f} đ)"
                for item in items if str(item.get("kind", "")).upper() not in allowed]
    if rejected:
        return failed(
            f"CCR {ccr:g}% dưới {threshold:g}% nên TSBĐ phải thuộc "
            f"{'/'.join(sorted(allowed))}; có {len(rejected)}/{len(items)} tài sản không "
            f"hợp lệ: " + ", ".join(rejected)
        )
    return passed(
        f"CCR {ccr:g}% dưới {threshold:g}% và toàn bộ {len(items)} TSBĐ đều thuộc "
        f"{'/'.join(sorted(allowed))}"
    )


def check_requested_vs_approved(facts: Facts, settings: dict) -> Verdict:
    """Approving more than the customer asked for is an operational signal."""

    requested = float(facts.get("doc.proposal.requested_limit"))
    approved = float(facts.get("los.approved_limit"))

    if approved > requested:
        return failed(
            f"HMTD phê duyệt {approved:,.0f} đ vượt mức khách hàng đề nghị "
            f"{requested:,.0f} đ, chênh {approved - requested:,.0f} đ"
        )
    return passed(
        f"HMTD phê duyệt {approved:,.0f} đ không vượt mức khách hàng đề nghị "
        f"{requested:,.0f} đ"
    )


def check_collateral_matches_dossier(facts: Facts, settings: dict) -> Verdict:
    """Collateral listed in the application matches what the systems hold."""

    declared = facts.get("doc.proposal.collateral_items")
    on_system = facts.get("collateral.items")
    threshold = float(settings["variance_threshold_pct"])

    declared_total = sum(float(item.get("value") or 0) for item in declared)
    system_total = sum(float(item.get("value") or 0) for item in on_system)
    declared_kinds = {norm_text(item.get("category")) for item in declared if item.get("category")}
    system_kinds = {norm_text(item.get("kind")) for item in on_system if item.get("kind")}

    problems: list[str] = []
    difference = variance_pct(declared_total, system_total)
    if difference is not None and difference > threshold:
        problems.append(
            f"tổng giá trị kê trong hồ sơ {declared_total:,.0f} đ so với trên hệ thống "
            f"{system_total:,.0f} đ, chênh {difference:.1f}% vượt ngưỡng {threshold:g}%"
        )
    only_declared = declared_kinds - system_kinds
    only_system = system_kinds - declared_kinds
    if only_declared:
        problems.append("loại có trong hồ sơ mà hệ thống không có: " + ", ".join(sorted(only_declared)))
    if only_system:
        problems.append("loại có trên hệ thống mà hồ sơ không kê: " + ", ".join(sorted(only_system)))

    if problems:
        return failed("TSBĐ hồ sơ và hệ thống không khớp — " + "; ".join(problems))
    return passed(
        f"TSBĐ khớp: {len(declared)} tài sản kê trong hồ sơ, tổng {declared_total:,.0f} đ, "
        f"cùng loại và cùng giá trị với {len(on_system)} tài sản trên hệ thống"
    )


def _pledged_at_cic(facts: Facts) -> list[dict]:
    """CIC assets with no release date - the security still live on the bureau."""

    return [item for item in facts.get("cic.collateral_items")
            if not item.get("released_on")]


def check_cic_security_live(facts: Facts, settings: dict) -> Verdict:
    """A facility booked as secured must have security still pledged at CIC."""

    ccr = float(facts.get("t24.ccr"))
    threshold = float(settings["unsecured_ccr_pct"])
    registered = facts.get("cic.collateral_items")
    pledged = _pledged_at_cic(facts)

    if ccr >= threshold:
        return passed(
            f"CCR {ccr:g}% không dưới {threshold:g}% nên không ràng buộc tài sản đăng "
            f"ký tại CIC ({len(registered)} tài sản trên R20)"
        )
    if not pledged:
        released = [f"{item['kind'] or 'không rõ loại'} giải chấp {item['released_on']}"
                    for item in registered if item.get("released_on")]
        return failed(
            f"CCR {ccr:g}% dưới {threshold:g}% nhưng CIC không còn tài sản nào đang thế "
            f"chấp: " + (", ".join(released) if released
                         else "báo cáo R20 không có tài sản bảo đảm nào")
        )
    return passed(
        f"CCR {ccr:g}% dưới {threshold:g}% và CIC còn {len(pledged)}/{len(registered)} "
        f"tài sản đang thế chấp"
    )


def check_cic_collateral_value(facts: Facts, settings: dict) -> Verdict:
    """Collateral value on the systems against what is registered at CIC."""

    threshold = float(settings["variance_threshold_pct"])
    on_system = facts.get("collateral.items")
    pledged = _pledged_at_cic(facts)

    system_total = sum(float(item.get("value") or 0) for item in on_system)
    cic_total = sum(float(item.get("value") or 0) for item in pledged)

    difference = variance_pct(system_total, cic_total)
    summary = (
        f"TSBĐ trên hệ thống {system_total:,.0f} đ ({len(on_system)} tài sản) so với "
        f"đăng ký tại CIC {cic_total:,.0f} đ ({len(pledged)} tài sản đang thế chấp)"
    )
    if difference is None:
        return failed(f"{summary} — cả hai đều bằng 0, không đánh giá được")
    if difference > threshold:
        return failed(f"{summary}, chênh {difference:.1f}% vượt ngưỡng {threshold:g}%")
    return passed(f"{summary}, chênh {difference:.1f}% trong ngưỡng {threshold:g}%")
