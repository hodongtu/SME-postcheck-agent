"""Findings -> Markdown, poured into src/templates/post-check-template.md.

There is no LLM in this file. The verdict table is what somebody signs, so
Python writes it: the same findings.json always renders the same report.

The template owns the shape - headings, order, which criteria sit under which
section - so changing the report means editing one Markdown file. This module
owns only the values: the tables, the summary, the appendix. The two commentary
paragraphs are the single exception, written by a model and spliced in as
values like any other.

Identifiers and comments are English; every string the reviewer reads is
Vietnamese.
"""

from __future__ import annotations

from src.facts import FACT_KEYS, Facts
from src.report.templates import Template, get_template
from src.rules.engine import Finding, summarise


TEMPLATE_NAME = "post-check-template"

STATUS_MARK = {"PASS": "Đạt", "FAIL": "**Không đạt**", "INSUFFICIENT_DATA": "_Thiếu dữ liệu_"}

EMPTY_TABLE = "_Không có tiêu chí nào trong mục này._"
EMPTY_COMMENTARY = "_Chưa có nhận định cho mục này._"

# Which collection rows belong to which part of section 1, and which facts each
# row stands for. Kept here rather than in the template because it is a mapping
# between data and prose, not a matter of layout.
COLLECTION_ROWS: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    "1.1": (
        ("Thông tin khách hàng và HMTD được PD trên hệ thống BEP", "BEP", ("bep.",)),
        ("Thông tin/ hồ sơ KH cung cấp", "Tài liệu upload",
         ("doc.financials.", "doc.proposal.", "doc.customer_name_values",
          "doc.tax_code_values", "doc.address_values", "doc.owner_name_values",
          "doc.owner_id_number_values", "doc.owner_birth_year_values",
          "doc.document_date_values", "doc.document_number_values",
          "doc.signature_and_seal", "doc.types_present", "doc.extensions",
          "doc.industry_on_registration")),
        ("Thông tin/ hồ sơ ĐVKD đánh giá", "Tài liệu upload",
         ("doc.industry_on_sitevisit",)),
    ),
    "1.2": (
        ("CIC KH/Chủ doanh nghiệp", "Database & Tài liệu upload", ("cic.",)),
        ("BL/WL của Khách hàng/Chủ doanh nghiệp", "Database & Tài liệu upload", ("blwl.",)),
        ("Limit và dư nghĩa vụ tại TCB", "Database", ()),
        ("Tài sản đảm bảo", "Database", ("collateral.",)),
        ("Thông tin bên thứ ba (Virac) và giao dịch dòng tiền", "Database & Virac",
         ("virac.", "cashflow.")),
    ),
}


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


def _summary(findings: list[Finding]) -> str:
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

    if counts["INSUFFICIENT_DATA"]:
        lines += ["", (
            f"> {counts['INSUFFICIENT_DATA']} tiêu chí chưa kiểm được vì thiếu dữ liệu. "
            f"Hồ sơ chưa rà soát xong; xem phụ lục cuối báo cáo."
        )]
    return "\n".join(lines)


def _collection_status(prefixes: tuple[str, ...], facts: Facts | None) -> str:
    """Whether the data a section-1 row stands for actually arrived."""

    if not prefixes:
        return "Chưa thu thập — không tiêu chí nào sử dụng dữ liệu này"
    paths = [path for path in FACT_KEYS
             if any(path == prefix or path.startswith(prefix) for prefix in prefixes)]
    if not paths:
        return "—"
    if facts is None:
        return f"{len(paths)} mục dữ liệu"
    collected = [path for path in paths if facts.has(path)]
    if len(collected) == len(paths):
        return f"Đã thu thập {len(collected)}/{len(paths)}"
    if not collected:
        return f"Chưa thu thập — thiếu cả {len(paths)}/{len(paths)} mục"
    return f"Thu thập một phần {len(collected)}/{len(paths)}"


def _collection_table(part: str, facts: Facts | None) -> str:
    lines = ["| Dữ liệu thu thập | Nguồn | Trạng thái |", "|---|---|---|"]
    for label, source, prefixes in COLLECTION_ROWS[part]:
        lines.append(f"| {_cell(label)} | {source} | {_collection_status(prefixes, facts)} |")
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
        source, description = FACT_KEYS.get(path, ("—", path))
        lines.append(f"| {_cell(description)} | {source} | {', '.join(blocked[path])} |")
    return "\n".join(lines)


def build_values(
    template: Template,
    findings: list[Finding],
    meta: dict,
    commentary: dict[str, str],
    facts: Facts | None,
) -> dict[str, str]:
    """One value per placeholder the template asks for.

    Driven by what the template wants, not by what this module happens to
    produce: a section added to the template appears here as a missing value,
    and Template.render refuses to print a report with the hole in it.
    """

    by_id = {finding.rule_id: finding for finding in findings}
    values: dict[str, str] = {
        "TenKhachHang": meta.get("customer_name", "—"),
        "MaSoThue": meta.get("tax_code", "—"),
        "ChuongTrinh": meta.get("program", "—"),
        "NgayRaSoat": meta.get("postcheck_date", "—"),
        "TongHop": _summary(findings),
        "PhuLucThieuDuLieu": _appendix(findings),
    }

    for name in template.placeholders():
        kind, _, section = name.partition(":")
        if kind == "BangTieuChi":
            rule_ids = template.rules_of(section)
            values[name] = _criteria_table(
                [by_id[rule_id] for rule_id in rule_ids if rule_id in by_id]
            )
        elif kind == "BangThuThap":
            values[name] = _collection_table(section, facts)
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
