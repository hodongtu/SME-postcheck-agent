"""BRD 2.4 - Early identification of credit risk signals.

Unlike group 2.3.b, this group reads internal and third-party information
updated to the review date, not the state at approval time.

The functions here DECIDE; they do not declare. Which of them is a rule, under
what id, title and severity, and on which facts, is in src/rules/registry.py -
one catalogue for all of them, so there is one place to look.
"""

from src.facts import Facts
from src.rules.criteria import SHAREHOLDER_PREFIX, _subjects_on_list
from src.rules.engine import Verdict, failed, passed, variance_pct


def check_debt_group_now(facts: Facts, settings: dict) -> Verdict:
    threshold = int(settings["debt_group_warning_threshold"])
    customer = int(facts.get("cic.customer_debt_group_at_postcheck"))
    owner = int(facts.get("cic.owner_debt_group_at_postcheck"))
    reviewed_on = facts.get("case.postcheck_date")

    flagged = [f"{label} nhóm {group}" for label, group in (("KH", customer), ("CDN", owner))
               if group >= threshold]
    if flagged:
        return failed(
            f"Tra cứu CIC ngày {reviewed_on}: {', '.join(flagged)} — từ nhóm {threshold} "
            f"trở lên là nợ cần chú ý/nợ xấu"
        )
    return passed(
        f"Tra cứu CIC ngày {reviewed_on}: KH nhóm {customer}, CDN nhóm {owner}, dưới "
        f"ngưỡng cảnh báo {threshold}"
    )


def check_blwl_now(facts: Facts, settings: dict) -> Verdict:
    reviewed_on = facts.get("case.postcheck_date")
    listed = [label for label, path in
              (("KH", "blwl.customer_at_postcheck"), ("CDN", "blwl.owner_at_postcheck"))
              if facts.get(path)]
    if listed:
        return failed(
            f"Tra cứu BL/WL ngày {reviewed_on}: {' và '.join(listed)} có tên trong danh sách"
        )
    return passed(
        f"Tra cứu BL/WL ngày {reviewed_on}: KH và CDN đều không có tên trong danh sách"
    )


def check_amc_now(facts: Facts, settings: dict) -> Verdict:
    """Is the company or its representative in a recovery workflow right now."""

    reviewed_on = facts.get("case.postcheck_date")
    listed = _subjects_on_list(facts, "amc", "postcheck", shareholders=False)
    if listed:
        return failed(
            f"Tra cứu AMC ngày {reviewed_on}: {' và '.join(listed)} đang ở luồng thu hồi nợ"
        )
    return passed(
        f"Tra cứu AMC ngày {reviewed_on}: KH và CDN đều không ở luồng thu hồi nợ"
    )


def check_shareholders_now(facts: Facts, settings: dict) -> Verdict:
    """The shareholders at review time, across all three lookups.

    The twin of C06, which asks the same question of the approval date. Kept
    apart from E01 and E02 so that a company whose shareholders LOS never
    recorded still gets its own debt group and BL/WL graded.
    """

    reviewed_on = facts.get("case.postcheck_date")
    threshold = int(settings["debt_group_warning_threshold"])
    groups = facts.get("cic.shareholder_debt_groups_at_postcheck") or {}

    problems = [f"{name} nhóm nợ {group}" for name, group in groups.items()
                if group is not None and int(group) >= threshold]
    for prefix, what in (("blwl", "BL/WL"), ("amc", "luồng thu hồi nợ AMC")):
        for item in _subjects_on_list(facts, prefix, "postcheck"):
            if item.startswith(SHAREHOLDER_PREFIX):
                problems.append(f"{item} nằm trong {what}")

    if problems:
        return failed(
            f"Tra cứu ngày {reviewed_on}: {len(problems)} dấu hiệu trên nhóm cổ đông — "
            + "; ".join(problems)
        )
    return passed(
        f"Tra cứu ngày {reviewed_on}: {len(groups)} cổ đông đều dưới nhóm nợ "
        f"{threshold}, không ai trong BL/WL hay luồng thu hồi nợ AMC"
    )


def _variance_verdict(
    left_label: str, left: float, right_label: str, right: float, threshold: float
) -> Verdict:
    difference = variance_pct(left, right)
    if difference is None:
        return failed(f"{left_label} và {right_label} đều bằng 0, không đánh giá được chênh lệch")
    summary = (
        f"{left_label} {left:,.0f} đ so với {right_label} {right:,.0f} đ, "
        f"chênh lệch {difference:.1f}%"
    )
    if difference > threshold:
        return failed(f"{summary} — vượt ngưỡng {threshold:g}%")
    return passed(f"{summary} — trong ngưỡng {threshold:g}%")


def check_sto_vs_application(facts: Facts, settings: dict) -> Verdict:
    """STO revenue against the statements the RM keyed in.

    Compared against the RM's own entry rather than the credit application: both
    sides then come from a query, so the criterion is decidable on every run
    instead of waiting on an extraction pass over the application document.
    """

    return _variance_verdict(
        "DT STO trên LOS", float(facts.get("los.sto_revenue")),
        f"DT trên BCTC RM nhập năm {facts.get('los.financials_online.report_year')}",
        float(facts.get("los.financials_online.revenue")),
        float(settings["variance_threshold_pct"]),
    )


def check_financials_vs_virac(facts: Facts, settings: dict) -> Verdict:
    """Statements against Virac, strictly for the same reporting period.

    EQUAL, not within a band: Virac derives its figures from the statements the
    company filed, so for one period the two are the same document read twice.
    Any difference is a discrepancy to look at, not a tolerance to spend.
    """

    year = str(int(facts.get("doc.financials.report_year")))
    virac_revenue = facts.get("virac.revenue_by_year")
    virac_profit = facts.get("virac.net_profit_by_year")

    absent = [name for name, table in (("doanh thu", virac_revenue), ("LNST", virac_profit))
              if year not in {str(key) for key in table}]
    if absent:
        return failed(
            f"Virac không có {' và '.join(absent)} của kỳ {year} nên không so được cùng kỳ "
            f"(Virac có: {', '.join(sorted(str(key) for key in virac_revenue))})"
        )

    def _lookup(table: dict) -> float:
        return float(next(value for key, value in table.items() if str(key) == year))

    pairs = (
        ("DT", float(facts.get("doc.financials.revenue_current_year")),
         _lookup(virac_revenue)),
        ("LNST", float(facts.get("doc.financials.net_profit_current_year")),
         _lookup(virac_profit)),
    )
    details = [f"{label} {year}: BCTC {filed:,.0f} đ, Virac {third:,.0f} đ"
               for label, filed, third in pairs]
    differing = [f"{label} lệch {abs(filed - third):,.0f} đ"
                 for label, filed, third in pairs if filed != third]

    if differing:
        return failed("; ".join(details) + " — " + "; ".join(differing))
    return passed("; ".join(details) + " — khớp tuyệt đối")


def check_revenue_swing(facts: Facts, settings: dict) -> Verdict:
    return _variance_verdict(
        "DT kỳ trước trên BCTC", float(facts.get("doc.financials.revenue_prior_year")),
        "DT kỳ báo cáo", float(facts.get("doc.financials.revenue_current_year")),
        float(settings["variance_threshold_pct"]),
    )


def check_cashflow(facts: Facts, settings: dict) -> Verdict:
    """PDLD is Payment due LD - an overdue disbursement, so the count is a fault
    count, not an activity count. More is worse, and the configured number is a
    ceiling."""

    count = int(facts.get("cashflow.pdld_count"))
    maximum = int(settings["max_pdld_count"])
    if count > maximum:
        return failed(f"Có {count} LD quá hạn (PDLD), vượt mức cho phép {maximum}")
    return passed(f"Có {count} LD quá hạn (PDLD), trong mức cho phép {maximum}")
