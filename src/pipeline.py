"""Five steps, in order, with no shared state.

SME_creditmemo needs a LangGraph StateGraph because it has four agent branches
and a blocking condition. Post-check has one path, so a one-branch graph would
only be function calls written the long way.

One run reviews ONE credit application. There is no batch mode.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.agents.calculator.financial_ratio_calculator import FinancialRatioCalculator
from src.agents.documents.document_classification import (
    _longest_filename_hit,
    rule_classify_document,
)
from src.agents.documents.document_discovery import compute_file_hash, group_from_path
from src.agents.documents.document_matrix import get_type
from src.agents.extraction.financial_statement_extraction import PERIOD_LABEL_PREFIX
from src.agents.extraction.structured_extraction import (
    resolve_money_multiplier,
    scale_amount,
)
from src.passes import run_extraction_passes
from src.facts import FACT_KEYS, MISSING, Facts
from src.report.commentary import build_commentary
from src.report.render import render_report
from src.rules.engine import Finding, run_rules, summarise
from src.rules.registry import RULES
from src.settings import get_settings
from src.tools import bcde, bep, t24, virac
from src.types import PostcheckDocument, to_dict_list
from src.utils.common import SUPPORTED_EXTENSIONS, normalize_text
from src.utils.reading.extractors import extract_document_text


NO_EXECUTOR = "chưa cấu hình query_executor nên không truy vấn được hệ thống"

CUSTOMER_CIC_TYPE = "cic_khach_hang_vay"
OWNER_CIC_TYPE = "cic_dai_dien_phap_luat_co_dong"


class MultipleCasesError(RuntimeError):
    """The input directory holds more than one dossier."""


@dataclass
class PostcheckResult:
    facts: Facts
    findings: list[Finding]
    documents: list[PostcheckDocument]
    report_markdown: str
    counts: dict[str, int]
    extraction_calls: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "extraction_calls": self.extraction_calls,
            "findings": [asdict(finding) for finding in self.findings],
            "facts": self.facts.to_dict(),
            "documents": to_dict_list(self.documents),
        }


# ---------------------------------------------------------------------------
# 1. Read the dossier
# ---------------------------------------------------------------------------

def read_case_documents(case_dir: Path, config: Any) -> list[PostcheckDocument]:
    """Find the files of ONE case, read their text, identify each by filename.

    EVERY file in the upload boxes becomes a document, including formats the
    readers cannot open. That matters for rule P03: the regulation lists the
    permitted formats, and a dossier holding a phone photo instead of a document
    is a P03 failure. Dropping unreadable files before the rules see them would
    make P03 pass on a dossier full of JPEGs - a check that cannot see the
    violation it exists to catch.

    The single-case guard matters more than it looks. Upload boxes are the
    subdirectories of a case, so pointing at a parent folder that holds several
    cases would merge two customers' documents into one Facts and the rules
    would grade a dossier that does not exist. That is silent and severe, so it
    raises.
    """

    case_root = Path(case_dir).resolve()
    documents: list[PostcheckDocument] = []
    strays: list[str] = []
    seen_hashes: set[str] = set()

    for path in sorted(case_root.rglob("*")):
        if not path.is_file() or path.name.startswith((".", "~$")):
            continue
        resolved = path.resolve()
        if resolved.parent.parent != case_root:
            strays.append(str(resolved.relative_to(case_root)))
            continue
        if len(documents) >= config.max_files:
            break

        file_hash = compute_file_hash(str(resolved))
        if file_hash in seen_hashes:
            continue
        seen_hashes.add(file_hash)

        document = PostcheckDocument(
            path=str(resolved),
            filename=resolved.name,
            declared_group=group_from_path(str(resolved)),
            file_hash=file_hash,
        )

        if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
            document.extraction_status = "unsupported"
            document.extraction_error = (
                f"không có bộ đọc cho định dạng '{resolved.suffix.lower()}'; "
                f"file vẫn được tính vào tiêu chí định dạng"
            )
        else:
            try:
                document.content = extract_document_text(
                    str(resolved), ocr_timeout_seconds=config.ocr_timeout_seconds
                )[: config.max_chars_per_document]
            except Exception as exc:                  # noqa: BLE001
                document.extraction_status = "failed"
                document.extraction_error = f"{type(exc).__name__}: {exc}"[:300]

        _identify(document, config)
        documents.append(document)

    if strays:
        raise MultipleCasesError(
            f"{case_root} looks like it holds more than one dossier: "
            f"{len(strays)} file(s) sit deeper than <case>/<upload box>/<file>, "
            f"e.g. {strays[:3]}. Point run_postcheck at a single case directory."
        )
    return documents


def _identify(document: PostcheckDocument, config: Any) -> None:
    """Name the checklist item this file is, or leave it unnamed.

    filename_keyword_owner alone is not enough here: it returns nothing when two
    types match the name, because SME_creditmemo settles that with an LLM
    classifier this pipeline does not have. Three CIC reports all match the
    keyword "thong tin cic", so every one of them would come back unidentified
    and the R20 pass would never run. rule_classify_document scores them and
    breaks the tie by how much of the filename the winning keyword covers.

    Below the confidence threshold the document stays unnamed on purpose. An
    uncertain guess would route one CIC report's debt group onto the wrong
    subject; an unnamed document leaves the fact missing, which the rules report
    honestly.
    """

    verdict = rule_classify_document(
        document.filename, document.content, document.declared_group
    )
    confidence = float(verdict.get("confidence") or 0.0)
    type_id = str(verdict.get("document_type") or "")

    if type_id and _more_specific_name_match(document, verdict):
        document.document_type_note = (
            "nhận diện theo từ khoá dài hơn hẳn trong tên file, dù điểm bằng nhau"
        )
        document.document_type = type_id
        document.document_group = get_type(type_id).group_id
        return

    if type_id and confidence < config.document_classifier_min_confidence:
        document.document_type_note = (
            f"không nhận diện được chắc chắn: ứng viên gần nhất là '{type_id}' "
            f"với độ tin cậy {confidence:.2f}, dưới ngưỡng "
            f"{config.document_classifier_min_confidence:.2f}"
        )
        type_id = ""
    elif not type_id:
        document.document_type_note = "không đầu mục hồ sơ nào khớp tên file"

    document.document_type = type_id
    document_type = get_type(type_id) if type_id else None
    document.document_group = (
        document_type.group_id if document_type else document.declared_group
    )


def _more_specific_name_match(document: PostcheckDocument, verdict: dict) -> bool:
    """True when the winner did not merely tie - it matched a longer name.

    Three CIC reports score identically because one of them claims the short
    keyword "thong tin cic", which is a substring of the other two. The
    confidence formula reads that as a coin toss, since it only looks at the
    score margin. But a keyword covering 29 characters of the filename against
    one covering 13 is not a coin toss: it is the more specific match, and the
    classifier's own tie-break already picked it. This says so out loud rather
    than discarding a correct answer for looking uncertain.
    """

    scores = verdict.get("scores") or {}
    winner = verdict.get("document_type") or ""
    name = normalize_text(document.filename)
    best = _longest_filename_hit(winner, name)
    if best <= 0:
        return False
    rivals = [
        _longest_filename_hit(type_id, name)
        for type_id, score in scores.items()
        if type_id != winner and score > 0
    ]
    return bool(rivals) and best > max(rivals)


# ---------------------------------------------------------------------------
# 2. Reference data
# ---------------------------------------------------------------------------

# Systems the pipeline queries. Anything FACT_KEYS attributes to one of them is
# filled by a query and by nothing else, so the list of such facts is read off
# the catalogue rather than copied beside it: a hand-kept copy that drifts is a
# fact quietly NOT marked missing when no executor is configured.
DB_SOURCES = frozenset({"BEP", "T24", "BCDE", "Virac"})


def _db_facts() -> tuple[str, ...]:
    """Every fact a system query fills, read off the source column of FACT_KEYS."""

    return tuple(
        path for path, (source, _) in FACT_KEYS.items() if source in DB_SOURCES
    )

_BEP_FIELDS: tuple[tuple[str, str], ...] = (
    ("bep.customer_name", "ten_kh"), ("bep.tax_code", "mst"), ("bep.address", "dia_chi"),
    ("bep.owner_name", "ten_cdn"), ("bep.owner_id_number", "cccd_cdn"),
    ("bep.owner_birth_year", "nam_sinh_cdn"), ("bep.gso_code", "ma_gso"),
    ("bep.industry", "nganh_nghe"), ("bep.program", "chuong_trinh"),
    ("bep.approved_limit", "hmtd_phe_duyet"),
    ("bep.approved_limit_by_product", "hmtd_phe_duyet_theo_sp"),
    ("bep.batch_valid_from", "batch_hieu_luc_tu"),
    ("bep.batch_valid_to", "batch_het_hieu_luc"),
    ("bep.sto_revenue", "dt_sto"),
)


def _query(facts: Facts, paths: tuple[str, ...], label: str, call, unpack) -> None:
    """One query. However it fails, it leaves a reason on the facts it owed.

    Three ways out, all ending in a marked-missing fact: the tool raised, the
    query returned nothing, or the row lacked the column. None of them may leave
    a fact silently absent, because the rule reading it must be able to say why.
    """

    try:
        result = call()
    except Exception as exc:                          # noqa: BLE001 - the reason must reach the report
        for path in paths:
            facts.mark_missing(path, f"{label} lỗi: {type(exc).__name__}: {exc}"[:200])
        return

    if not result:
        for path in paths:
            facts.mark_missing(path, f"{label} không trả về dữ liệu cho khách hàng này")
        return

    values = unpack(result)
    for path in paths:
        value = values.get(path)
        if value is None:
            facts.mark_missing(path, f"{label} không có trường tương ứng")
        else:
            facts.set(path, value, reason=f"{label} trả về giá trị rỗng")


def fetch_reference_data(
    facts: Facts,
    tax_code: str,
    config: Any,
    approval_date: str,
    postcheck_date: str,
) -> None:
    """Fill every fact that comes from a system query."""

    executor = config.query_executor
    if executor is None:
        for path in _db_facts():
            facts.mark_missing(path, NO_EXECUTOR)
        return

    def _call(tool_object, **kwargs):
        return tool_object.invoke({"tax_code": tax_code, "executor": executor, **kwargs})

    _query(facts, tuple(path for path, _ in _BEP_FIELDS), "Truy vấn BEP",
           lambda: _call(bep.get_bep_approval),
           lambda row: {path: row.get(column) for path, column in _BEP_FIELDS})

    _query(facts,
           ("t24.booking_date", "t24.active_limit",
            "t24.active_limit_by_product", "t24.ccr"),
           "Truy vấn T24",
           lambda: _call(t24.get_t24_facilities),
           lambda row: {f"t24.{key}": value for key, value in row.items()})

    _query(facts, ("collateral.items",), "Truy vấn TSBĐ",
           lambda: _call(t24.get_collateral),
           lambda items: {"collateral.items": items})

    _query(facts,
           ("cic.customer_debt_group_at_approval", "cic.owner_debt_group_at_approval"),
           "Truy vấn CIC trên BCDE",
           lambda: _call(bcde.get_bcde_cic),
           lambda row: {"cic.customer_debt_group_at_approval": row.get("customer"),
                        "cic.owner_debt_group_at_approval": row.get("owner")})

    _query(facts, ("blwl.customer_at_approval", "blwl.owner_at_approval"),
           "Truy vấn BL/WL trên BCDE",
           lambda: _call(bcde.get_bcde_blwl),
           lambda row: {"blwl.customer_at_approval": row.get("customer"),
                        "blwl.owner_at_approval": row.get("owner")})

    _query(facts, ("virac.revenue_by_year", "virac.net_profit_by_year"),
           "Truy vấn Virac",
           lambda: _call(virac.get_virac_financials),
           lambda row: {f"virac.{key}": value for key, value in row.items()})

    _query(facts, ("cashflow.pdld_count",), "Truy vấn giao dịch dòng tiền",
           lambda: _call(t24.get_cashflow_pdld,
                         from_date=approval_date, to_date=postcheck_date),
           lambda row: {"cashflow.pdld_count": row.get("pdld_count")})


# ---------------------------------------------------------------------------
# 3. Facts from the dossier
#
# Amounts are read straight out of the passes. Each pass already multiplied by
# the unit its own page declared (proposal_extraction.normalize_amounts and its
# siblings), so scaling again here would be wrong by a factor of a million.
# ---------------------------------------------------------------------------

# fact path <- (extraction slot, block, field within the block)
_IDENTITY_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("doc.customer_name_values", "financial_statement", "customer", "ten"),
    ("doc.customer_name_values", "proposal", "customer", "ten"),
    ("doc.customer_name_values", "sitevisit", "customer", "ten"),
    ("doc.customer_name_values", "cic_s10a", "khach_hang", "ten"),
    ("doc.customer_name_values", "cic_r20", "khach_hang", "ten"),
    ("doc.tax_code_values", "financial_statement", "customer", "ma_so_thue"),
    ("doc.tax_code_values", "proposal", "customer", "ma_so_thue"),
    ("doc.tax_code_values", "sitevisit", "customer", "ma_so_thue"),
    ("doc.tax_code_values", "cic_s10a", "khach_hang", "ma_so_thue"),
    ("doc.tax_code_values", "cic_r20", "khach_hang", "ma_so_thue"),
    ("doc.address_values", "cic_s10a", "khach_hang", "dia_chi"),
    ("doc.address_values", "cic_r20", "khach_hang", "dia_chi"),
    ("doc.owner_name_values", "cic_s10a", "khach_hang", "nguoi_dai_dien"),
    ("doc.owner_name_values", "cic_r20", "khach_hang", "nguoi_dai_dien"),
    ("doc.document_date_values", "sitevisit", "survey_info", "survey_date"),
    ("doc.document_date_values", "cic_s10a", "bao_cao", "ngay_gui"),
    ("doc.document_date_values", "cic_r20", "bao_cao", "ngay_gui"),
)

_FINANCIAL_METRICS: tuple[tuple[str, str], ...] = (
    ("doc.financials.total_assets", "total_assets"),
    ("doc.financials.total_capital", "total_capital"),
    ("doc.financials.revenue_current_year", "net_revenue"),
    ("doc.financials.net_profit_current_year", "net_profit"),
)

_NO_SOURCE_DOCUMENT = {
    "doc.customer_name_values": "không chứng từ nào trích xuất được tên khách hàng",
    "doc.tax_code_values": "không chứng từ nào trích xuất được mã số thuế",
    "doc.address_values": "hồ sơ không có báo cáo CIC, hoặc không đọc được địa chỉ trên đó",
    "doc.owner_name_values": "hồ sơ không có báo cáo CIC, hoặc không đọc được người đại diện",
    "doc.document_date_values": "không chứng từ nào trích xuất được ngày lập",
}


def _block_value(document: PostcheckDocument, slot: str, block: str, key: str) -> Any:
    payload = getattr(document, slot)
    if not isinstance(payload, dict):
        return None
    section = payload.get(block)
    if not isinstance(section, dict):
        return None
    value = section.get(key)
    return value if value not in (None, "") else None


def _iso_date(value: Any) -> Any:
    """CIC prints dd/mm/yyyy; the rules read ISO. Anything else passes through."""

    text = str(value or "").strip()
    parts = text.split("/")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        day, month, year = parts
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value


def _debt_group(payload: Any, settings: dict) -> tuple[int | None, str]:
    """The worst debt group a CIC report shows, mapped from its printed label."""

    if not isinstance(payload, dict):
        return None, "không đọc được báo cáo CIC"
    labels = [str(row.get("nhom_no") or "").strip()
              for row in payload.get("du_no_hien_tai") or []
              if str(row.get("nhom_no") or "").strip()]
    if not labels:
        return None, "báo cáo CIC không ghi nhóm nợ"

    table = {normalize_text(key): value
             for key, value in (settings.get("debt_group_by_label") or {}).items()}
    groups = [table[normalize_text(label)] for label in labels
              if normalize_text(label) in table]
    if not groups:
        return None, (
            "nhóm nợ trên báo cáo CIC ghi là "
            + ", ".join(f"“{label}”" for label in sorted(set(labels)))
            + " — chưa khai trong debt_group_by_label"
        )
    return max(int(group) for group in groups), ""


def assemble_document_facts(
    facts: Facts, documents: list[PostcheckDocument], settings: dict
) -> None:
    """Write every fact whose source is the dossier."""

    collected: dict[str, list[dict[str, Any]]] = {}
    for path, slot, block, key in _IDENTITY_SOURCES:
        for document in documents:
            value = _block_value(document, slot, block, key)
            if value is None:
                continue
            if path == "doc.document_date_values":
                value = _iso_date(value)
            collected.setdefault(path, []).append(
                {"filename": document.filename, "value": value}
            )
    for path, reason in _NO_SOURCE_DOCUMENT.items():
        facts.set(path, collected.get(path, []), reason=reason)

    facts.set(
        "doc.types_present",
        sorted({d.document_type for d in documents if d.document_type}),
        reason="không file nào khớp đầu mục hồ sơ nào theo tên file",
    )
    facts.set(
        "doc.extensions",
        [{"filename": d.filename, "extension": d.extension} for d in documents],
        reason="không tìm thấy file nào trong các thư mục upload",
    )

    sitevisits = [d for d in documents if isinstance(d.sitevisit, dict)]
    facts.set(
        "doc.industry_on_sitevisit",
        next((v for d in sitevisits
              if (v := _block_value(d, "sitevisit", "business_profile", "industry"))), None),
        reason="hồ sơ không có báo cáo khảo sát thực địa, hoặc không đọc được ngành nghề trên đó",
    )

    _assemble_cic_collateral(facts, documents)
    _assemble_financials(facts, documents)
    _assemble_proposal(facts, documents)
    _assemble_cic(facts, documents, settings)


def _assemble_cic_collateral(facts: Facts, documents: list[PostcheckDocument]) -> None:
    """Collateral as registered at CIC, from the R20 loan-security report.

    A third, independent view of the security behind the facility, beside T24
    (what the bank booked) and the credit application (what the customer
    declared). `ngay_giai_chap` is the one that matters most: an empty release
    date means the asset is still pledged, and a filled one means it is not -
    a facility booked as secured against a released asset is a real finding.

    `gia_tri_trieu_vnd` is already in VND despite the name saying millions: the
    R20 pass multiplies it by a million on the way out. Do not scale it again.
    """

    reports = [d for d in documents if isinstance(d.cic_r20, dict)]
    if not reports:
        facts.mark_missing(
            "cic.collateral_items",
            "hồ sơ không có báo cáo CIC R20 về tài sản bảo đảm",
        )
        return

    items: list[dict[str, Any]] = []
    for document in reports:
        for row in document.cic_r20.get("tai_san_bao_dam") or []:
            if not isinstance(row, dict):
                continue
            items.append({
                "lender": row.get("tctd") or "",
                "kind": row.get("loai_tai_san") or "",
                "description": row.get("mo_ta_tai_san") or "",
                "value": row.get("gia_tri_trieu_vnd"),
                "released_on": row.get("ngay_giai_chap") or None,
            })
    facts.set("cic.collateral_items", items,
              reason="báo cáo CIC R20 không liệt kê tài sản bảo đảm nào")


def _assemble_financials(facts: Facts, documents: list[PostcheckDocument]) -> None:
    """Pull the figures the rules need out of every statement in the dossier.

    A dossier may carry several statements: the current year as a scan and the
    prior year as an e-tax filing, or one period in both formats at once. Two
    consequences, and neither is decided here by hand.

    WHICH FIGURE WINS is FinancialRatioCalculator's answer, not ours. It merges
    by (period, metric) and ranks candidates by (source, tier, score), and its
    SOURCE_RANK puts "xml" above "llm" - a figure read exactly out of a tax
    filing beats the same figure guessed from a scan. All this function owes it
    is the source marker, which it used to withhold by passing "". Setting it is
    the whole of "the filing wins for that period".

    WHICH PERIOD IS THE REPORT is the latest period found anywhere in the
    dossier. It used to be resolve_report_years(statements[0]) - the period of
    whichever file sorted first by name, which is to say the alphabet decided
    what rule P07 was checking.

    Metric matching is likewise FinancialRatioCalculator's: statement code
    first, then accent-stripped alias, with an exclude list. Note that the
    e-tax path deliberately leaves the code empty, because the B01a-DNN form
    numbers its indicators differently from the TT200 scheme those codes belong
    to; the alias match is the correct route there.

    "Latest period" assumes annual statements. A quarterly filing collapses onto
    the same year label as the annual one for that year, and the two would then
    compete. The BRD only ever speaks of annual statements, so that is left
    alone rather than half-handled.
    """

    statements = [d for d in documents if isinstance(d.financial_statement, dict)]
    reason = (
        "hồ sơ không có BCTC" if not statements
        else "pass BCTC không đọc được chỉ tiêu này"
    )
    if not statements:
        for path, _ in _FINANCIAL_METRICS:
            facts.mark_missing(path, reason)
        facts.mark_missing("doc.financials.report_year", reason)
        facts.mark_missing("doc.financials.revenue_prior_year", reason)
        return

    payloads = [
        {
            "financial_statement_extraction": document.financial_statement,
            "financial_statement_extraction_source":
                document.financial_statement.get("extraction_source", ""),
        }
        for document in statements
    ]
    by_year = FinancialRatioCalculator().extract_yearly_metrics(payloads)

    years = sorted(
        int(label.removeprefix(PERIOD_LABEL_PREFIX))
        for label in by_year
        if label.removeprefix(PERIOD_LABEL_PREFIX).isdigit()
    )
    if not years:
        for path, _ in _FINANCIAL_METRICS:
            facts.mark_missing(path, reason)
        facts.mark_missing("doc.financials.report_year", "BCTC không nêu kỳ báo cáo")
        facts.mark_missing("doc.financials.revenue_prior_year", "BCTC không nêu kỳ báo cáo")
        return

    current, prior = years[-1], (years[-2] if len(years) > 1 else None)
    facts.set("doc.financials.report_year", current)

    current_metrics = by_year.get(f"{PERIOD_LABEL_PREFIX}{current}", {})
    for path, metric in _FINANCIAL_METRICS:
        facts.set(path, current_metrics.get(metric), reason=reason)

    if prior is None:
        facts.mark_missing(
            "doc.financials.revenue_prior_year",
            f"hồ sơ chỉ có BCTC của một kỳ ({current}), không có kỳ trước để so sánh",
        )
    else:
        facts.set(
            "doc.financials.revenue_prior_year",
            by_year.get(f"{PERIOD_LABEL_PREFIX}{prior}", {}).get("net_revenue"),
            reason=f"BCTC kỳ {prior} không có chỉ tiêu doanh thu thuần",
        )


def _assemble_proposal(facts: Facts, documents: list[PostcheckDocument]) -> None:
    proposals = [d for d in documents if isinstance(d.proposal, dict)]
    reason = (
        "hồ sơ không có Đề nghị cấp tín dụng" if not proposals
        else "pass Đề nghị cấp tín dụng không đọc được mục này"
    )
    facts.set(
        "doc.proposal.declared_revenue",
        next((v for d in proposals
              if (v := _block_value(d, "proposal", "plan_efficiency", "revenue")) is not None),
             None),
        reason=reason,
    )
    facts.set(
        "doc.proposal.requested_limit",
        next((v for d in proposals
              if (v := _block_value(d, "proposal", "credit_request", "total_limit")) is not None),
             None),
        reason=reason,
    )
    items: list[dict[str, Any]] = []
    for document in proposals:
        collateral = (document.proposal or {}).get("collateral")
        if isinstance(collateral, dict):
            items.extend(item for item in collateral.get("items") or []
                         if isinstance(item, dict))
    facts.set("doc.proposal.collateral_items", items, reason=reason)


def _assemble_cic(
    facts: Facts, documents: list[PostcheckDocument], settings: dict
) -> None:
    """Debt groups read from the CIC reports filed with the dossier (BRD 2.4).

    Which report belongs to whom comes from the document type: the customer's
    own CIC report versus the legal representative's.
    """

    for path, type_id, who in (
        ("cic.customer_debt_group_at_postcheck", CUSTOMER_CIC_TYPE, "khách hàng"),
        ("cic.owner_debt_group_at_postcheck", OWNER_CIC_TYPE, "chủ doanh nghiệp"),
    ):
        reports = [d for d in documents
                   if d.document_type == type_id and isinstance(d.cic_s10a, dict)]
        if not reports:
            facts.mark_missing(
                path, f"hồ sơ không có báo cáo CIC của {who} tra cứu tại thời điểm post-check"
            )
            continue
        group, why = _debt_group(reports[0].cic_s10a, settings)
        if group is None:
            facts.mark_missing(path, why)
        else:
            facts.set(path, group)


# ---------------------------------------------------------------------------
# 4-5. Grade, then render
# ---------------------------------------------------------------------------

def run_postcheck(
    case_dir: str | Path,
    config: Any,
    tax_code: str,
    approval_date: str,
    postcheck_date: str,
) -> PostcheckResult:
    """Review ONE credit application, from its upload folder to a Markdown report.

    The report comes back finished, commentary included. It used to come back
    without it, and the caller rendered a second time to add it - so the report
    this function returned was never the one anybody read.

    This is the one place the pipeline spends on an LLM beyond extraction: with
    `config.commentary_llm` set, the two commentary paragraphs cost one call
    each. With it None, nothing is called and the report says so.
    """

    settings = get_settings()

    documents = read_case_documents(Path(case_dir), config)
    extraction_calls = run_extraction_passes(documents, config)

    facts = Facts()
    facts.set("case.postcheck_date", postcheck_date,
              reason="chưa truyền ngày rà soát vào run_postcheck")
    assemble_document_facts(facts, documents, settings)
    fetch_reference_data(facts, tax_code, config, approval_date, postcheck_date)
    facts.mark_manual_facts_missing()

    findings = run_rules(RULES, facts, settings)

    commentary = (
        build_commentary(findings, config.commentary_llm)
        if config.enable_commentary else {}
    )

    def _or_dash(path: str, fallback: str = "—") -> str:
        value = facts.get(path)
        return str(value) if value is not MISSING else fallback

    meta = {
        "customer_name": _or_dash("bep.customer_name"),
        "tax_code": _or_dash("bep.tax_code", tax_code),
        "program": _or_dash("bep.program"),
        "postcheck_date": postcheck_date,
    }
    return PostcheckResult(
        facts=facts,
        findings=findings,
        documents=documents,
        report_markdown=render_report(findings, meta, commentary, facts=facts),
        counts=summarise(findings),
        extraction_calls=extraction_calls,
    )
