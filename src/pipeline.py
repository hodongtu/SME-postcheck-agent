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
from src.agents.documents.document_matrix import (
    get_type,
    is_financial_statement_type,
    is_sitevisit_photo_type,
)
from src.agents.extraction.financial_statement_extraction import PERIOD_LABEL_PREFIX
from src.agents.extraction.structured_extraction import (
    resolve_money_multiplier,
    scale_amount,
)
from src.passes import run_extraction_passes
from src.facts import FACT_KEYS, MISSING, Facts, db_facts
from src.report.commentary import build_commentary
from src.report.render import render_report
from src.rules.engine import Finding, run_rules, summarise
from src.rules.registry import RULES
from src.settings import get_settings
from src.tools import amc, los, blwl, cic, portfolio, t24, virac
from src.types import PostcheckDocument, to_dict_list
from src.rules._compare import norm_digits
from src.utils.common import SUPPORTED_EXTENSIONS, normalize_text
from src.utils.reading.digital_signature import has_digital_signature
from src.utils.reading.extractors import extract_document_text


NO_EXECUTOR = "chưa cấu hình query_executor nên không truy vấn được hệ thống"


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
_LOS_FIELDS: tuple[tuple[str, str], ...] = (
    ("los.customer_name", "ten_kh"), ("los.tax_code", "mst"), ("los.address", "dia_chi"),
    ("los.owner_name", "ten_cdn"), ("los.owner_id_number", "cccd_cdn"),
    ("los.owner_birth_year", "nam_sinh_cdn"), ("los.gso_code", "ma_gso"),
    ("los.industry", "nganh_nghe"), ("los.persona", "chan_dung"),
    ("los.is_site_visit", "co_khao_sat_thuc_dia"),
    ("los.program", "chuong_trinh"),
    ("los.approved_limit", "hmtd_phe_duyet"),
    ("los.approved_limit_by_product", "hmtd_phe_duyet_theo_sp"),
    ("los.batch_valid_from", "batch_hieu_luc_tu"),
    ("los.batch_valid_to", "batch_het_hieu_luc"),
    ("los.sto_revenue", "dt_sto"),
    ("los.chief_accountant_name", "ten_ke_toan_truong"),
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


def _match_list(facts: Facts, entries: list[dict], prefix: str, moment: str) -> dict[str, Any]:
    """Match the company, its owner and its shareholders against one list.

    Shared by BL/WL and AMC: the two are different lists with the same shape, and
    a subject is in one if a tax code, a national ID, or - only when the entry
    carries neither - a name matches. Name matching is the weakest of the three
    and is the last resort precisely because a namesake is a false positive a
    person has to overrule.

    `False` is a real answer: the list was read and this subject is not in it -
    including when the list came back empty, which the business has decided means
    nobody is listed rather than a lookup that did not run.

    `None` is returned for a subject LOS gave us nothing to match on - with no
    identifier at all, "not in the list" would be a conclusion drawn from nothing,
    and `_query` turns the None into a marked-missing fact instead.

    The shareholder result is a dict keyed by name rather than a list of hits: an
    empty list would be indistinguishable from "no shareholder is listed", which
    is the ordinary case and a real answer, while an empty dict correctly means
    LOS recorded no shareholders.
    """

    def field(path: str) -> str:
        return str(facts.get(path)) if facts.has(path) else ""

    def hit(subject_tax_code: str, subject_id: str, subject_name: str) -> bool:
        for entry in entries:
            entry_tax = norm_digits(entry.get("tax_code"))
            entry_id = norm_digits(entry.get("id_number"))
            entry_name = normalize_text(str(entry.get("name") or ""))
            if subject_tax_code and entry_tax and subject_tax_code == entry_tax:
                return True
            if subject_id and entry_id and subject_id == entry_id:
                return True
            if subject_name and entry_name and not entry_tax and not entry_id \
                    and subject_name == entry_name:
                return True
        return False

    tax_code = norm_digits(field("los.tax_code"))
    owner_id = norm_digits(field("los.owner_id_number"))
    owner_name = normalize_text(field("los.owner_name"))

    shareholders: dict[str, bool] = {}
    for person in (facts.get("los.shareholders") if facts.has("los.shareholders") else []):
        name = str(person.get("name") or "").strip()
        if not name:
            continue
        shareholders[name] = hit(
            "", norm_digits(person.get("id_number")), normalize_text(name)
        )

    return {
        f"{prefix}.customer_at_{moment}": hit(tax_code, "", "") if tax_code else None,
        f"{prefix}.owner_at_{moment}":
            hit("", owner_id, owner_name) if (owner_id or owner_name) else None,
        f"{prefix}.shareholders_at_{moment}": shareholders,
    }


def fetch_reference_data(
    facts: Facts,
    tax_code: str,
    config: Any,
    approval_date: str,
    postcheck_date: str,
    settings: dict,
) -> None:
    """Fill every fact that comes from a system query."""

    executor = config.query_executor
    if executor is None:
        for path in db_facts():
            facts.mark_missing(path, NO_EXECUTOR)
        return

    def _call(tool_object, **kwargs):
        return tool_object.invoke({"tax_code": tax_code, "executor": executor, **kwargs})

    _query(facts, tuple(path for path, _ in _LOS_FIELDS), "Truy vấn LOS",
           lambda: _call(los.get_los_approval),
           lambda row: {path: row.get(column) for path, column in _LOS_FIELDS})

    _query(facts, ("los.shareholders",), "Truy vấn cổ đông trên LOS",
           lambda: _call(los.get_los_shareholders),
           lambda items: {"los.shareholders": items})

    _query(facts,
           ("los.sitevisit_online.industry", "los.sitevisit_online.address"),
           "Truy vấn khảo sát thực địa RM nhập trên LOS",
           lambda: _call(los.get_los_sitevisit_online),
           lambda row: {"los.sitevisit_online.industry": row.get("nganh_nghe"),
                        "los.sitevisit_online.address": row.get("dia_chi")})

    _query(facts,
           ("los.financials_online.report_year", "los.financials_online.report_type",
            "los.financials_online.revenue", "los.financials_online.net_profit"),
           "Truy vấn BCTC RM nhập trên LOS",
           lambda: _call(los.get_los_financials_online),
           lambda row: {"los.financials_online.report_year": row.get("nam"),
                        "los.financials_online.report_type":
                            as_report_type(row.get("loai_bao_cao"), settings),
                        "los.financials_online.revenue": row.get("doanh_thu"),
                        "los.financials_online.net_profit": row.get("lnst")})

    _query(facts,
           ("t24.booking_date", "t24.active_limit",
            "t24.active_limit_by_product", "t24.ccr"),
           "Truy vấn T24",
           lambda: _call(t24.get_t24_facilities),
           lambda row: {f"t24.{key}": value for key, value in row.items()})

    _query(facts, ("collateral.items",), "Truy vấn TSBĐ",
           lambda: _call(t24.get_collateral),
           lambda items: {"collateral.items": items})

    _query(facts, ("t24.outstanding",), "Truy vấn dư nợ",
           lambda: _call(t24.get_outstanding),
           lambda row: {"t24.outstanding": row.get("outstanding")})

    # CIC and BL/WL are the same lookup at two moments: the approval date and the
    # review date. One tool each, called twice - a report in the dossier could
    # only ever carry one of the two.
    for moment, as_of in (("approval", approval_date), ("postcheck", postcheck_date)):
        _query(facts,
               (f"cic.customer_debt_group_at_{moment}", f"cic.owner_debt_group_at_{moment}"),
               f"Truy vấn CIC tại thời điểm {as_of}",
               lambda as_of=as_of: _call(cic.get_cic_debt_groups, as_of_date=as_of),
               lambda row, moment=moment: {
                   f"cic.customer_debt_group_at_{moment}":
                       as_debt_group(row.get("customer"), settings),
                   f"cic.owner_debt_group_at_{moment}":
                       as_debt_group(row.get("owner"), settings),
               })

        _query(facts, (f"cic.shareholder_debt_groups_at_{moment}",),
               f"Truy vấn nhóm nợ cổ đông tại thời điểm {as_of}",
               lambda as_of=as_of: cic.get_cic_shareholder_debt_groups.invoke({
                   "shareholders": (facts.get("los.shareholders")
                                    if facts.has("los.shareholders") else []),
                   "as_of_date": as_of, "executor": executor}),
               lambda by_person, moment=moment: {
                   f"cic.shareholder_debt_groups_at_{moment}": {
                       name: as_debt_group(group, settings)
                       for name, group in by_person.items()
                   }
               })

        # Lists, matched here rather than in SQL, so a hit can name its entry.
        for prefix, label, fetch in (
            ("blwl", "BL/WL", blwl.get_blacklist_watchlist),
            ("amc", "AMC", amc.get_amc_recovery_list),
        ):
            _query(facts,
                   (f"{prefix}.customer_at_{moment}", f"{prefix}.owner_at_{moment}",
                    f"{prefix}.shareholders_at_{moment}"),
                   f"Truy vấn danh sách {label} tại thời điểm {as_of}",
                   lambda as_of=as_of, fetch=fetch: _call(fetch, as_of_date=as_of),
                   lambda result, prefix=prefix, moment=moment:
                       _match_list(facts, result["entries"], prefix, moment))

    _query(facts, ("portfolio.facilities",), "Truy vấn danh mục tín dụng tại TCB",
           lambda: _call(portfolio.get_portfolio),
           lambda items: {"portfolio.facilities": items})

    _query(facts, ("cic.collateral_items",), "Truy vấn TSBĐ đăng ký tại CIC",
           lambda: _call(cic.get_cic_collateral),
           lambda items: {"cic.collateral_items": items})

    _query(facts, ("virac.revenue_by_year", "virac.net_profit_by_year"),
           "Truy vấn Virac",
           lambda: _call(virac.get_virac_financials),
           lambda row: {f"virac.{key}": value for key, value in row.items()})

    _query(facts, ("t24.transactions_by_period",), "Truy vấn giao dịch tài khoản",
           lambda: _call(t24.get_transaction_summary,
                         from_date=approval_date, to_date=postcheck_date),
           lambda items: {"t24.transactions_by_period": items})

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
#
# The CIC reports used to be the fourth source here, and the only one carrying an
# address or a representative's name. They are queried from the system now, so
# the address comes off the site visit instead - BRD row 14 names the site visit
# as a source in its own right - and the representative's name has no source at
# all. That is why doc.owner_name_values is declared in MANUAL_FACTS.
_IDENTITY_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("doc.customer_name_values", "financial_statement", "customer", "name"),
    ("doc.customer_name_values", "proposal", "customer", "name"),
    ("doc.customer_name_values", "sitevisit", "customer", "name"),
    ("doc.tax_code_values", "financial_statement", "customer", "tax_code"),
    ("doc.tax_code_values", "proposal", "customer", "tax_code"),
    ("doc.tax_code_values", "sitevisit", "customer", "tax_code"),
    ("doc.address_values", "sitevisit", "survey_info", "location"),
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
    "doc.address_values": "hồ sơ không có báo cáo khảo sát thực địa, hoặc không đọc được địa chỉ trên đó",
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


def as_debt_group(value: Any, settings: dict) -> Any:
    """A debt group as the rules want it: an integer 1-5.

    The view may return the number or the printed Vietnamese label, so both are
    accepted. A label absent from `debt_group_by_label` returns None, which the
    caller turns into a marked-missing fact - it is never guessed as group 1.
    """

    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    table = {normalize_text(key): number
             for key, number in (settings.get("debt_group_by_label") or {}).items()}
    return table.get(normalize_text(text))


def as_report_type(value: Any, settings: dict) -> Any:
    """What KIND of financial report this is, as one of the configured names.

    Both sides of V09 print their own wording - the RM types one thing into LOS,
    the statement's own form name says another - so both come through here and
    land on the same vocabulary. A wording the table does not know returns None,
    which the caller turns into a marked-missing fact: the alternative is two
    strings that differ for no reason anybody can act on.
    """

    if not value:
        return None
    table = {normalize_text(key): name
             for key, name in (settings.get("financial_report_types") or {}).items()}
    return table.get(normalize_text(str(value)))


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

    _assemble_signature(facts, documents)
    _assemble_photo_evidence(facts, documents)
    _assemble_financials(facts, documents, settings)
    _assemble_proposal(facts, documents)


def _assemble_photo_evidence(
    facts: Facts, documents: list[PostcheckDocument]
) -> None:
    """What the vision pass saw in each site-visit photograph (V10).

    Collected from every photo document, so one unreadable file does not hide
    what the others showed. No photos at all leaves the fact missing; whether
    that is a problem is P02's question, decided from the LOS site-visit flag.
    """

    # LOS said no field visit is needed, so "no photo evidence" is the correct
    # and complete answer - not a gap. Recorded as an empty finding rather than
    # marked missing, so V10 can pass instead of reading as unchecked.
    if facts.has("los.is_site_visit") and not facts.get("los.is_site_visit"):
        facts.set_empty(
            "doc.sitevisit_photo_evidence",
            "LOS không yêu cầu khảo sát thực địa nên hồ sơ không cần ảnh",
        )
        return

    photos = [document for document in documents
              if document.document_type
              and is_sitevisit_photo_type(document.document_type)]

    evidence = []
    for document in photos:
        payload = document.sitevisit_photos
        for entry in (payload.get("photos") if isinstance(payload, dict) else None) or []:
            evidence.append({
                "filename": entry.get("filename") or document.filename,
                "markers": entry.get("markers") or [],
                "note": entry.get("description") or "",
            })

    facts.set(
        "doc.sitevisit_photo_evidence", evidence,
        reason=(
            "hồ sơ không có ảnh khảo sát thực địa" if not photos
            else f"pass ảnh không đọc được {len(photos)} ảnh khảo sát trong hồ sơ"
        ),
    )


def _assemble_signature(facts: Facts, documents: list[PostcheckDocument]) -> None:
    """P05: do the financial statements carry a digital signature.

    Selected by DOCUMENT TYPE, not by whether extraction read the figures: the
    signature is a property of the file, and a statement the model failed to
    parse is still signed or unsigned. Tying this to the extraction result would
    have made an LLM outage look like an unsigned filing.

    One signed statement is enough. All of them unsigned is a real answer. A
    dossier whose statements are all in formats the detector cannot judge - a
    .docx, an .xlsx - leaves the fact MISSING rather than claiming unsigned.
    """

    statements = [document for document in documents
                  if document.document_type
                  and is_financial_statement_type(document.document_type)]
    if not statements:
        facts.mark_missing("doc.financials.has_digital_signature", "hồ sơ không có BCTC")
        return

    judged = [value for value in
              (has_digital_signature(document.path) for document in statements)
              if value is not None]
    facts.set(
        "doc.financials.has_digital_signature",
        True if any(judged) else (False if judged else None),
        reason=(
            "chưa đọc được chữ ký số trên định dạng BCTC trong hồ sơ ("
            + ", ".join(sorted({document.extension for document in statements})) + ")"
        ),
    )


def _assemble_financials(
    facts: Facts, documents: list[PostcheckDocument], settings: dict
) -> None:
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
        facts.mark_missing("doc.financials.report_type", reason)
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
        facts.mark_missing("doc.financials.report_type", reason)
        facts.mark_missing("doc.financials.report_year", "BCTC không nêu kỳ báo cáo")
        facts.mark_missing("doc.financials.revenue_prior_year", "BCTC không nêu kỳ báo cáo")
        return

    current, prior = years[-1], (years[-2] if len(years) > 1 else None)
    facts.set("doc.financials.report_year", current)

    # V09 compares the KIND of report, and the statements name their own kind
    # differently on each path - the e-tax filing gives its form name, the model
    # gives its three-way vocabulary. Both land on the configured names or on
    # nothing; an audited statement says so on its own and outranks the form name.
    kinds = []
    for document in statements:
        payload = document.financial_statement
        if (payload.get("audit_opinion") or {}).get("is_audited"):
            kinds.append(as_report_type("bao cao kiem toan", settings))
        kinds.append(as_report_type(payload.get("document_type"), settings))
    known = [kind for kind in kinds if kind]
    facts.set("doc.financials.report_type", known[0] if known else None,
              reason="không nhận ra loại báo cáo; bổ sung vào financial_report_types")

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
    extraction_calls = run_extraction_passes(documents, config, settings)

    facts = Facts()
    facts.set("case.postcheck_date", postcheck_date,
              reason="chưa truyền ngày rà soát vào run_postcheck")
    # Systems BEFORE documents: _assemble_photo_evidence has to know whether LOS
    # asked for a site visit at all, and nothing in the document assembly reads a
    # system fact - so this order costs nothing and buys that one answer.
    fetch_reference_data(facts, tax_code, config, approval_date, postcheck_date,
                         settings)
    assemble_document_facts(facts, documents, settings)
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
        "customer_name": _or_dash("los.customer_name"),
        "tax_code": _or_dash("los.tax_code", tax_code),
        "program": _or_dash("los.program"),
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
