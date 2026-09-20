"""The fact sheet: the single boundary between collection and rule checking.

Everything to the left of this module may be slow and may fail - OCR, LLM
passes, SQL. Everything to the right is a pure function over `Facts`, which is
why the whole rule suite is testable offline from a JSON fixture.

A fact is either present or MISSING. There is no third state and no implicit
default: a rule that needs a fact nobody collected must not run at all.

Keys and identifiers are English. Descriptions and reason strings are
Vietnamese because they are printed verbatim into the report the reviewer
reads.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, NamedTuple


class _Missing:
    """The absence of a fact. Falsy, and loudly named in any report it reaches."""

    __slots__ = ()

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "«thiếu dữ liệu»"


MISSING = _Missing()

DEFAULT_MISSING_REASON = "chưa thu thập được"


# ---------------------------------------------------------------------------
# The vocabulary a fact is described with.
#
# CATEGORY and DELIVERY are two different questions, and they used to be one
# column. They separated the moment the business put the RM's online entries in
# the DOCUMENTS group: those are document data (category) that arrives from a
# query (delivery). One column cannot say both, and the half that would have been
# lost is the one that decides whether a fact gets marked missing when no
# database is wired - so the report would have gone quiet instead of saying the
# lookup never ran.
# ---------------------------------------------------------------------------

# The seven groups the business compares between. CASE is not one of them: it is
# the run's own parameter, not data about the customer.
LOS       = "LOS"
T24       = "T24"
PORTFOLIO = "Portfolio"
LISTS     = "BL/WL & AMC"
CIC       = "CIC"
VIRAC     = "Virac"
DOCUMENTS = "Chứng từ"
CASE      = "Hồ sơ"

CATEGORIES: tuple[str, ...] = (LOS, T24, PORTFOLIO, LISTS, CIC, VIRAC, DOCUMENTS, CASE)

# Who fills the fact. QUERY is the one with teeth: db_facts() reads it, and every
# QUERY fact is marked missing when config.query_executor is None.
QUERY, DOSSIER, RUN = "query", "dossier", "run"
DELIVERIES: tuple[str, ...] = (QUERY, DOSSIER, RUN)


class FactSpec(NamedTuple):
    """One fact's identity: what kind of data it is, who fills it, what it says."""

    category: str     # one of CATEGORIES - how the report groups it
    delivery: str     # one of DELIVERIES - who fills it
    description: str  # Vietnamese; printed into the report


# ---------------------------------------------------------------------------
# The fact catalogue.
#
# THIS IS THE SOURCE OF TRUTH for what a rule may read. `registry.py` checks
# every rule's `needs` against these keys at import time, so a typo in a fact
# path raises when the notebook opens rather than quietly becoming an
# unchecked row in a report somebody signs.
# ---------------------------------------------------------------------------
FACT_KEYS: dict[str, FactSpec] = {
    # --- LOS: what was approved (BRD 1.1) ----------------------------------
    "los.customer_name":            FactSpec(LOS, QUERY, "Tên khách hàng trên hệ thống phê duyệt"),
    "los.tax_code":                 FactSpec(LOS, QUERY, "Mã số thuế"),
    "los.address":                  FactSpec(LOS, QUERY, "Địa chỉ khách hàng"),
    "los.owner_name":               FactSpec(LOS, QUERY, "Tên chủ doanh nghiệp"),
    "los.owner_id_number":          FactSpec(LOS, QUERY, "Số CCCD của chủ doanh nghiệp"),
    "los.owner_birth_year":         FactSpec(LOS, QUERY, "Năm sinh của chủ doanh nghiệp"),
    "los.gso_code":                 FactSpec(LOS, QUERY, "Mã ngành GSO của khách hàng"),
    "los.industry":                 FactSpec(LOS, QUERY, "Tên ngành nghề của khách hàng trên LOS"),
    "los.persona":                  FactSpec(LOS, QUERY, "Chân dung khách hàng: sản xuất, thương mại, dịch vụ…"),
    "los.is_site_visit":            FactSpec(LOS, QUERY, "Hồ sơ có yêu cầu khảo sát thực địa"),
    "los.program":                  FactSpec(LOS, QUERY, "Chương trình cấp tín dụng (B1CP/MISA/PLPP)"),
    "los.approved_limit":           FactSpec(LOS, QUERY, "Tổng HMTD được phê duyệt, đồng"),
    "los.approved_limit_by_product":FactSpec(LOS, QUERY, "HMTD phê duyệt theo từng sản phẩm, đồng"),
    "los.batch_valid_from":         FactSpec(LOS, QUERY, "Ngày lô phê duyệt bắt đầu hiệu lực"),
    "los.batch_valid_to":           FactSpec(LOS, QUERY, "Ngày lô phê duyệt hết hiệu lực"),
    "los.sto_revenue":              FactSpec(LOS, QUERY, "Doanh thu STO trên LOS, đồng"),
    "los.chief_accountant_name":    FactSpec(LOS, QUERY, "Tên kế toán trưởng trên hồ sơ LOS"),
    # Shape: [{"name": str, "id_number": str, "stake_pct": float}, ...]
    "los.shareholders":             FactSpec(LOS, QUERY, "Top 5 cổ đông góp vốn trên LOS"),

    # --- LOS: what the RM keyed in, to compare against the documents filed ---
    "los.sitevisit_online.industry":      FactSpec(DOCUMENTS, QUERY, "Ngành nghề trên khảo sát thực địa RM nhập"),
    "los.sitevisit_online.address":       FactSpec(DOCUMENTS, QUERY, "Địa chỉ trên khảo sát thực địa RM nhập"),
    "los.financials_online.report_year":  FactSpec(DOCUMENTS, QUERY, "Năm báo cáo của BCTC RM nhập"),
    "los.financials_online.report_type":  FactSpec(DOCUMENTS, QUERY, "Loại báo cáo của BCTC RM nhập"),
    "los.financials_online.revenue":      FactSpec(DOCUMENTS, QUERY, "Doanh thu trên BCTC RM nhập, đồng"),
    "los.financials_online.net_profit":   FactSpec(DOCUMENTS, QUERY, "LNST trên BCTC RM nhập, đồng"),

    # --- T24: what was actually booked (BRD 2.3.c) -------------------------
    "t24.booking_date":             FactSpec(T24, QUERY, "Ngày hạch toán HMTD"),
    "t24.active_limit":             FactSpec(T24, QUERY, "Tổng HMTD đã active, đồng"),
    "t24.active_limit_by_product":  FactSpec(T24, QUERY, "HMTD đã active theo từng sản phẩm, đồng"),
    "t24.ccr":                      FactSpec(T24, QUERY, "CCR hạch toán trên BBC, phần trăm"),
    "t24.outstanding":              FactSpec(T24, QUERY, "Dư nợ (dư nghĩa vụ) tại TCB, đồng"),
    "cashflow.pdld_count":          FactSpec(T24, QUERY, "Số LD quá hạn (PDLD) phát sinh"),
    # Shape: the view's rows, carried through as they arrive
    "t24.transactions_by_period":   FactSpec(T24, QUERY,
                                             "Giao dịch tài khoản theo kỳ, từ phê duyệt đến rà soát"),
    # Shape: [{"kind": str, "value": float}, ...]
    "collateral.items":             FactSpec(T24, QUERY, "Danh sách TSBĐ trên hệ thống: loại và giá trị"),

    # --- CIC and BL/WL: the same two lookups at two moments (BRD 1.2, 2.4) -
    # Both are queried, not read from the dossier, because a file could only ever
    # carry one of the two dates.
    "cic.customer_debt_group_at_approval":  FactSpec(CIC, QUERY, "Nhóm nợ của KH tại thời điểm phê duyệt"),
    "cic.owner_debt_group_at_approval":     FactSpec(CIC, QUERY, "Nhóm nợ của CDN tại thời điểm phê duyệt"),
    "cic.customer_debt_group_at_postcheck": FactSpec(CIC, QUERY, "Nhóm nợ của KH tại thời điểm post-check"),
    "cic.owner_debt_group_at_postcheck":    FactSpec(CIC, QUERY, "Nhóm nợ của CDN tại thời điểm post-check"),
    # Shape for the shareholder entries: {shareholder name: bool, ...}. A dict, not
    # a list of hits: an empty list would be indistinguishable from "no shareholder
    # is listed", which is the common case and a real answer.
    "cic.shareholder_debt_groups_at_approval":  FactSpec(CIC, QUERY, "Nhóm nợ của từng cổ đông tại thời điểm phê duyệt"),
    "cic.shareholder_debt_groups_at_postcheck": FactSpec(CIC, QUERY, "Nhóm nợ của từng cổ đông tại thời điểm post-check"),
    "blwl.customer_at_approval":            FactSpec(LISTS, QUERY, "KH có trong BL/WL tại thời điểm phê duyệt"),
    "blwl.owner_at_approval":               FactSpec(LISTS, QUERY, "CDN có trong BL/WL tại thời điểm phê duyệt"),
    "blwl.shareholders_at_approval":        FactSpec(LISTS, QUERY, "Từng cổ đông có trong BL/WL tại thời điểm phê duyệt"),
    "blwl.customer_at_postcheck":           FactSpec(LISTS, QUERY, "KH có trong BL/WL tại thời điểm post-check"),
    "blwl.owner_at_postcheck":              FactSpec(LISTS, QUERY, "CDN có trong BL/WL tại thời điểm post-check"),
    "blwl.shareholders_at_postcheck":       FactSpec(LISTS, QUERY, "Từng cổ đông có trong BL/WL tại thời điểm post-check"),
    "amc.customer_at_approval":             FactSpec(LISTS, QUERY, "KH ở luồng thu hồi nợ tại thời điểm phê duyệt"),
    "amc.owner_at_approval":                FactSpec(LISTS, QUERY, "CDN ở luồng thu hồi nợ tại thời điểm phê duyệt"),
    "amc.shareholders_at_approval":         FactSpec(LISTS, QUERY, "Từng cổ đông ở luồng thu hồi nợ tại thời điểm phê duyệt"),
    "amc.customer_at_postcheck":            FactSpec(LISTS, QUERY, "KH ở luồng thu hồi nợ tại thời điểm post-check"),
    "amc.owner_at_postcheck":               FactSpec(LISTS, QUERY, "CDN ở luồng thu hồi nợ tại thời điểm post-check"),
    "amc.shareholders_at_postcheck":        FactSpec(LISTS, QUERY, "Từng cổ đông ở luồng thu hồi nợ tại thời điểm post-check"),

    # --- Portfolio: a secondary source, derived from the systems above -----
    # Shape: the view's rows, carried through as they arrive
    "portfolio.facilities":         FactSpec(PORTFOLIO, QUERY, "Danh mục tín dụng của khách hàng tại TCB"),

    # --- Third party: Virac is the only one (BRD 2.4) ----------------------
    "virac.revenue_by_year":        FactSpec(VIRAC, QUERY, "Doanh thu theo năm, đồng"),
    "virac.net_profit_by_year":     FactSpec(VIRAC, QUERY, "Lợi nhuận sau thuế theo năm, đồng"),

    # --- Dossier: identity read off the documents (BRD 1.1) ----------------
    # One fact per field rather than a single blob. If they were bundled, a
    # rule comparing "customer name" would run over an empty list and report a
    # pass when no document carried a name at all. Split, the runner's
    # missing-data gate covers the field level for free.
    # Shape: [{"filename": str, "value": Any}, ...]
    "doc.customer_name_values":     FactSpec(DOCUMENTS, DOSSIER, "Tên KH đọc được trên từng chứng từ"),
    "doc.tax_code_values":          FactSpec(DOCUMENTS, DOSSIER, "Mã số thuế đọc được trên từng chứng từ"),
    "doc.address_values":           FactSpec(DOCUMENTS, DOSSIER, "Địa chỉ đọc được trên từng chứng từ"),
    "doc.owner_name_values":        FactSpec(DOCUMENTS, DOSSIER, "Tên chủ doanh nghiệp đọc được trên từng chứng từ"),
    "doc.owner_id_number_values":   FactSpec(DOCUMENTS, DOSSIER, "Số CCCD đọc được trên từng chứng từ"),
    "doc.owner_birth_year_values":  FactSpec(DOCUMENTS, DOSSIER, "Năm sinh CDN đọc được trên từng chứng từ"),
    # Shape: [{"filename": str, "type_id": str, "has_signature": bool, "has_seal": bool}, ...]
    "doc.signature_and_seal":       FactSpec(DOCUMENTS, DOSSIER, "Tình trạng chữ ký và con dấu của từng chứng từ"),
    "doc.types_present":            FactSpec(DOCUMENTS, DOSSIER, "Các đầu mục hồ sơ nhận diện được theo tên file"),
    "doc.extensions":               FactSpec(DOCUMENTS, DOSSIER, "Định dạng của từng file trong hồ sơ"),
    "doc.industry_on_registration": FactSpec(DOCUMENTS, DOSSIER, "Ngành nghề ghi trên giấy đăng ký kinh doanh"),
    "doc.industry_on_sitevisit":    FactSpec(DOCUMENTS, DOSSIER, "Ngành nghề ĐVKD ghi nhận khi khảo sát thực địa"),
    # Shape: [{"filename": str, "markers": [str, ...], "note": str}, ...]
    "doc.sitevisit_photo_evidence": FactSpec(DOCUMENTS, DOSSIER, "Dấu hiệu nhận được trên từng ảnh khảo sát thực địa"),

    # --- Dossier: financial statements -------------------------------------
    "doc.financials.report_year":            FactSpec(DOCUMENTS, DOSSIER, "Năm của kỳ báo cáo tài chính"),
    "doc.financials.report_type":            FactSpec(DOCUMENTS, DOSSIER, "Loại báo cáo tài chính nộp kèm"),
    "doc.financials.total_assets":           FactSpec(DOCUMENTS, DOSSIER, "Tổng tài sản trên BCTC, đồng"),
    "doc.financials.total_capital":          FactSpec(DOCUMENTS, DOSSIER, "Tổng nguồn vốn trên BCTC, đồng"),
    "doc.financials.revenue_prior_year":     FactSpec(DOCUMENTS, DOSSIER, "Doanh thu kỳ trước trên BCTC, đồng"),
    "doc.financials.revenue_current_year":   FactSpec(DOCUMENTS, DOSSIER, "Doanh thu kỳ báo cáo trên BCTC, đồng"),
    "doc.financials.net_profit_current_year":FactSpec(DOCUMENTS, DOSSIER, "Lợi nhuận sau thuế kỳ báo cáo trên BCTC, đồng"),
    "doc.financials.has_digital_signature":  FactSpec(DOCUMENTS, DOSSIER, "BCTC có chữ ký điện tử"),

    # Shape: [{"lender", "kind", "description", "value", "released_on"}, ...]
    "cic.collateral_items":         FactSpec(CIC, QUERY, "TSBĐ của khách hàng đã đăng ký tại CIC"),

    # --- Dossier: credit application ---------------------------------------
    "doc.proposal.declared_revenue":FactSpec(DOCUMENTS, DOSSIER, "Doanh thu khách hàng kê khai trên Đề nghị vay vốn, đồng"),
    "doc.proposal.requested_limit": FactSpec(DOCUMENTS, DOSSIER, "Tổng HMTD khách hàng đề nghị, đồng"),
    "doc.proposal.collateral_items":FactSpec(DOCUMENTS, DOSSIER, "TSBĐ khách hàng kê trong Đề nghị vay vốn"),

    # --- The review itself --------------------------------------------------
    "case.postcheck_date":          FactSpec(CASE, RUN, "Ngày thực hiện rà soát post-check"),
}


# No extraction pass reads these fields, and this version deliberately does not
# add one. Rules that need them always stop at INSUFFICIENT_DATA. Declared here
# so that "nobody collects this" is a stated decision rather than an oversight;
# `verify_manual_facts` asserts this set matches reality in both directions.
# The reason strings are Vietnamese: they are printed into the report appendix.
MANUAL_FACTS: dict[str, str] = {
    "doc.owner_name_values":                 "chưa có nguồn trích xuất; điền thủ công hoặc bổ sung pass",
    "doc.owner_id_number_values":            "chưa có nguồn trích xuất; điền thủ công hoặc bổ sung pass",
    "doc.owner_birth_year_values":           "chưa có nguồn trích xuất; điền thủ công hoặc bổ sung pass",
    "doc.industry_on_registration":          "chưa có pass đọc giấy đăng ký kinh doanh",
    "doc.signature_and_seal":                "chưa có pass nhận diện chữ ký và con dấu",
}


# Facts collected for the report's section 1.2 that NO rule grades yet. Declared
# for the same reason as MANUAL_FACTS: `verify_needs_paths` otherwise reads "no
# rule reads this" as a fact collected for nothing, which is exactly the right
# default. Being in this dict makes it a decision instead, and the check asserts
# the set both ways - a path here that a rule DOES read is also an error.
DISPLAY_ONLY_FACTS: dict[str, str] = {
    "t24.outstanding": "dư nợ; tiêu chí so sánh với dòng tiền khách hàng sẽ bổ sung sau",
    "portfolio.facilities": "danh mục tín dụng; chưa có tiêu chí đối chiếu",
    "t24.transactions_by_period": "giao dịch tài khoản; phần được chấm là E06 (LD quá hạn)",
    "los.sitevisit_online.address": "địa chỉ RM nhập; V08 chỉ đối chiếu ngành nghề",
    "doc.proposal.declared_revenue": "DT kê trên ĐNVV; E04 nay đối chiếu DT STO với BCTC RM nhập",
    "los.financials_online.net_profit": "LNST RM nhập; V09 chỉ đối chiếu kỳ và loại báo cáo",
    "los.chief_accountant_name": "kế toán trưởng; chưa có tiêu chí đối chiếu",
}


def db_facts() -> tuple[str, ...]:
    """Every fact a system query fills, read off the delivery column of FACT_KEYS.

    Lives here, not in pipeline.py, because it is a statement about FACT_KEYS -
    and because both the collector and the report need it, and the report cannot
    import the pipeline that imports it.
    """

    return tuple(path for path, spec in FACT_KEYS.items() if spec.delivery == QUERY)


class UnknownFactError(KeyError):
    """A path nobody declared in FACT_KEYS."""


def _is_empty(value: Any) -> bool:
    """Empty means absent. 0 and False are values, not absences."""

    if value is None or value is MISSING:
        return True
    if isinstance(value, (str, bytes)):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict, frozenset)):
        return len(value) == 0
    return False


class Facts:
    """Every fact the rules may read, plus why the absent ones are absent."""

    def __init__(
        self,
        values: dict[str, Any] | None = None,
        reasons: dict[str, str] | None = None,
    ) -> None:
        self._values: dict[str, Any] = {}
        self._reasons: dict[str, str] = dict(reasons or {})
        self._empty_notes: dict[str, str] = {}
        for path, value in (values or {}).items():
            self.set(path, value)

    # -- writing ------------------------------------------------------------

    def set(self, path: str, value: Any, *, reason: str = "") -> None:
        """Record a fact. An empty value is recorded as absent, never as a value."""

        if path not in FACT_KEYS:
            raise UnknownFactError(
                f"'{path}' is not declared in FACT_KEYS (src/facts.py). "
                f"Declare it there first, with its source and description."
            )
        if _is_empty(value):
            self.mark_missing(path, reason or DEFAULT_MISSING_REASON)
            return
        self._values[path] = value
        self._reasons.pop(path, None)

    def set_empty(self, path: str, note: str) -> None:
        """Record that a collection is legitimately EMPTY - an answer, not a gap.

        `set` treats an empty list as absent, and that default is right almost
        everywhere: "no documents carried a name" is a gap, not a finding. But
        occasionally emptiness IS the answer - no site-visit photographs, because
        LOS says this file needs no site visit - and a rule must be able to read
        that instead of stopping at insufficient data.

        Use it only where the emptiness has been REASONED to, never where a
        collector simply came back with nothing. `note` says which reasoning, and
        is kept so the appendix can explain an empty row.
        """

        if path not in FACT_KEYS:
            raise UnknownFactError(f"'{path}' is not declared in FACT_KEYS (src/facts.py).")
        self._values[path] = []
        self._empty_notes[path] = note
        self._reasons.pop(path, None)

    def mark_missing(self, path: str, reason: str) -> None:
        """Record that a fact could not be collected, and say why."""

        if path not in FACT_KEYS:
            raise UnknownFactError(f"'{path}' is not declared in FACT_KEYS (src/facts.py)")
        self._values.pop(path, None)
        self._reasons[path] = reason or DEFAULT_MISSING_REASON

    def mark_manual_facts_missing(self) -> None:
        """Flag every fact no collector fills, with the reason from MANUAL_FACTS."""

        for path, reason in MANUAL_FACTS.items():
            self.mark_missing(path, reason)

    # -- reading ------------------------------------------------------------

    def get(self, path: str) -> Any:
        """The fact, or MISSING. Raises for a path nobody declared."""

        if path not in FACT_KEYS:
            raise UnknownFactError(f"'{path}' is not declared in FACT_KEYS (src/facts.py)")
        return self._values.get(path, MISSING)

    def has(self, path: str) -> bool:
        return self.get(path) is not MISSING

    def missing(self, paths: Iterable[str]) -> list[str]:
        """Which of these paths are absent, in the order given."""

        return [path for path in paths if self.get(path) is MISSING]

    def reason(self, path: str) -> str:
        """Why a fact is absent, phrased for the report."""

        spec = FACT_KEYS.get(path)
        description = spec.description if spec else path
        return f"{description}: {self._reasons.get(path, DEFAULT_MISSING_REASON)}"

    # -- serialisation ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"values": dict(self._values), "reasons": dict(self._reasons)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Facts":
        return cls(payload.get("values"), payload.get("reasons"))

    @classmethod
    def from_json_file(cls, path: str) -> "Facts":
        with open(path, encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def collected(self) -> list[str]:
        return sorted(self._values)

    def __repr__(self) -> str:
        return f"Facts({len(self._values)}/{len(FACT_KEYS)} collected)"
