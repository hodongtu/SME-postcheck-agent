"""Findings -> Markdown, poured into src/templates/post-check-template.md. """

from src.facts import FACT_KEYS, Facts, db_facts
from src.report.templates import Template, get_template
from src.rules.engine import Finding, summarise


TEMPLATE_NAME = "post-check-template"

STATUS_MARK = {"PASS": "Đạt", "FAIL": "**Không đạt**", "INSUFFICIENT_DATA": "_Thiếu dữ liệu_"}

EMPTY_TABLE = "_Không có tiêu chí nào trong mục này._"
EMPTY_COMMENTARY = "_Chưa có nhận định cho mục này._"

def _cell(text: str) -> str:
    """One Markdown table cell: collapse newlines, escape the column separator."""

    return " ".join(str(text or "").split()).replace("|", "\\|")


def _criteria_table(findings: list[Finding]) -> str:
    if not findings:
        return EMPTY_TABLE
    header = (
        "| Mã | Nội dung kiểm tra | Kết quả | Ghi nhận thực tế | Yêu cầu | Mức độ |\n"
        "|---|---|---|---|---|---|\n"
    )
    rows = "".join(
        f"| {finding.rule_id} | {_cell(finding.title)} | {STATUS_MARK[finding.status]} "
        f"| {_cell(finding.observed)} | {_cell(finding.expected)} "
        f"| {finding.severity_label} |\n"
        for finding in findings
    )
    return header + rows


def _no_approval_record(facts: Facts | None) -> bool:
    """Did LOS hold no approval at all for this customer. """

    if facts is None:
        return False
    approval = [path for path in db_facts() if path.startswith("los.")]
    return bool(approval) and not any(facts.has(path) for path in approval)


def _summary(findings: list[Finding], facts: Facts | None = None) -> str:
    counts = summarise(findings)
    lines = [
        f"Đạt **{counts['PASS']}** · Không đạt **{counts['FAIL']}** · "
        f"Thiếu dữ liệu **{counts['INSUFFICIENT_DATA']}** trên tổng "
        f"{counts['TOTAL']} tiêu chí.",
    ]

    severe = [f for f in findings if f.status == "FAIL" and f.severity == "high"]
    if severe:
        lines += ["", f"**{len(severe)} tiêu chí không đạt ở mức độ cao:**", ""]
        lines += [f"- **{f.rule_id}** {f.title} — {_cell(f.observed)}" for f in severe]

    if _no_approval_record(facts):
        lines += ["", (
            "> **Không tìm thấy hồ sơ phê duyệt trên LOS cho mã số thuế này.** "
            "Không phải hồ sơ thiếu chứng từ: mã số thuế có thể không có trong hệ "
            "thống, hoặc kết nối cơ sở dữ liệu chưa được cấu hình. Kiểm tra lại mã số "
            "thuế và `query_executor` trước khi đọc các kết luận bên dưới."
        )]
    elif counts["INSUFFICIENT_DATA"]:
        lines += ["", (
            f"> {counts['INSUFFICIENT_DATA']} tiêu chí chưa kiểm được vì thiếu dữ liệu. "
            f"Hồ sơ chưa rà soát xong; xem phụ lục cuối báo cáo."
        )]
    return "\n".join(lines)


def _appendix(findings: list[Finding]) -> str:
    unchecked = [f for f in findings if f.status == "INSUFFICIENT_DATA"]
    if not unchecked:
        return "Không có. Toàn bộ tiêu chí đã kiểm được."

    blocked: dict[str, list[str]] = {}
    for finding in unchecked:
        for path in finding.missing:
            blocked.setdefault(path, []).append(finding.rule_id)

    lines = ["| Dữ liệu | Nguồn | Chặn tiêu chí |", "|---|---|---|"]
    for path in sorted(blocked):
        spec = FACT_KEYS.get(path)
        category = spec.category if spec else "—"
        description = spec.description if spec else path
        lines.append(f"| {_cell(description)} | {category} | {', '.join(blocked[path])} |")
    return "\n".join(lines)


def build_values(
    template: Template,
    findings: list[Finding],
    meta: dict,
    commentary: dict[str, str],
    facts: Facts | None,
) -> dict[str, str]:
    """One value per placeholder the template asks for. """

    by_id = {finding.rule_id: finding for finding in findings}
    values: dict[str, str] = {
        "TenKhachHang": meta.get("customer_name", "—"),
        "MaSoThue": meta.get("tax_code", "—"),
        "ChuongTrinh": meta.get("program", "—"),
        "NgayRaSoat": meta.get("postcheck_date", "—"),
        "TongHop": _summary(findings, facts),
        "PhuLucThieuDuLieu": _appendix(findings),
    }

    for name in template.placeholders():
        kind, _, section = name.partition(":")
        if kind == "BangTieuChi":
            rule_ids = template.rules_of(section)
            values[name] = _criteria_table(
                [by_id[rule_id] for rule_id in rule_ids if rule_id in by_id]
            )
        elif kind == "NhanDinh":
            values[name] = commentary.get(section, "").strip() or EMPTY_COMMENTARY

    return values


def render_report(
    findings: list[Finding],
    meta: dict,
    commentary: dict[str, str] | None = None,
    facts: Facts | None = None,
) -> str:
    """The complete report, in the shape the template lays out."""

    template = get_template(TEMPLATE_NAME)
    values = build_values(template, findings, meta, commentary or {}, facts)
    return template.render(values)
