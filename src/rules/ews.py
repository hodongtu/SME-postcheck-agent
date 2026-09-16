"""BRD 2.4 - Early identification of credit risk signals.

Unlike group 2.3.b, this group reads internal and third-party information
updated to the review date, not the state at approval time.
"""

from __future__ import annotations

from src.facts import Facts
from src.rules.engine import Rule, Verdict, failed, passed, variance_pct


def _check_debt_group_now(facts: Facts, settings: dict) -> Verdict:
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


def _check_blwl_now(facts: Facts, settings: dict) -> Verdict:
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


def _check_sto_vs_application(facts: Facts, settings: dict) -> Verdict:
    return _variance_verdict(
        "DT STO trên BEP", float(facts.get("bep.sto_revenue")),
        "DT trên ĐNVV", float(facts.get("doc.proposal.declared_revenue")),
        float(settings["variance_threshold_pct"]),
    )


def _check_financials_vs_virac(facts: Facts, settings: dict) -> Verdict:
    """Statements against Virac, strictly for the same reporting period."""

    threshold = float(settings["variance_threshold_pct"])
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

    verdicts = [
        _variance_verdict(
            f"DT {year} trên BCTC", float(facts.get("doc.financials.revenue_current_year")),
            f"DT {year} trên Virac", _lookup(virac_revenue), threshold),
        _variance_verdict(
            f"LNST {year} trên BCTC", float(facts.get("doc.financials.net_profit_current_year")),
            f"LNST {year} trên Virac", _lookup(virac_profit), threshold),
    ]
    breaches = [verdict.observed for verdict in verdicts if verdict.status == "FAIL"]
    if breaches:
        return failed("; ".join(breaches))
    return passed("; ".join(verdict.observed for verdict in verdicts))


def _check_revenue_swing(facts: Facts, settings: dict) -> Verdict:
    return _variance_verdict(
        "DT kỳ trước trên BCTC", float(facts.get("doc.financials.revenue_prior_year")),
        "DT kỳ báo cáo", float(facts.get("doc.financials.revenue_current_year")),
        float(settings["variance_threshold_pct"]),
    )


def _check_cashflow(facts: Facts, settings: dict) -> Verdict:
    count = int(facts.get("cashflow.pdld_count"))
    minimum = int(settings["min_pdld_count"])
    if count < minimum:
        return failed(f"Chỉ có {count} lần phát sinh PDLD, dưới mức tối thiểu {minimum}")
    return passed(f"Có {count} lần phát sinh PDLD, đạt mức tối thiểu {minimum}")


# Answers BRD rows 39, 40, 41, 43, 44, 45 (section 2.4).
RULES: tuple[Rule, ...] = (
    Rule("E01", "KH và CDN có nợ xấu, nợ có vấn đề tại thời điểm post-check",
         "Nhóm nợ CIC của KH và CDN dưới ngưỡng cảnh báo", "high",
         ("cic.customer_debt_group_at_postcheck", "cic.owner_debt_group_at_postcheck",
          "case.postcheck_date"), _check_debt_group_now),
    Rule("E02", "KH và CDN nằm trong BL/WL tại thời điểm post-check",
         "KH và CDN không có tên trong BL/WL", "high",
         ("blwl.customer_at_postcheck", "blwl.owner_at_postcheck",
          "case.postcheck_date"), _check_blwl_now),
    Rule("E03", "DT STO trên BEP so với DT trên ĐNVV",
         "Chênh lệch không quá 40%", "medium",
         ("bep.sto_revenue", "doc.proposal.declared_revenue"), _check_sto_vs_application),
    Rule("E04", "DT và LNST trên BCTC so với Virac",
         "Cùng kỳ báo cáo, chênh lệch không quá 40%", "medium",
         ("doc.financials.report_year", "doc.financials.revenue_current_year",
          "doc.financials.net_profit_current_year", "virac.revenue_by_year",
          "virac.net_profit_by_year"), _check_financials_vs_virac),
    Rule("E05", "DT trên BCTC biến động giữa kỳ trước và kỳ báo cáo",
         "Biến động không quá 40%", "medium",
         ("doc.financials.revenue_prior_year", "doc.financials.revenue_current_year"),
         _check_revenue_swing),
    Rule("E06", "Giao dịch dòng tiền: số lần phát sinh PDLD",
         "Số lần phát sinh PDLD đạt mức tối thiểu", "medium",
         ("cashflow.pdld_count",), _check_cashflow),
)
