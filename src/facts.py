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
from typing import Any, Iterable


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
# The fact catalogue: path -> (source system, Vietnamese description)
#
# THIS IS THE SOURCE OF TRUTH for what a rule may read. `registry.py` checks
# every rule's `needs` against these keys at import time, so a typo in a fact
# path raises when the notebook opens rather than quietly becoming an
# unchecked row in a report somebody signs.
# ---------------------------------------------------------------------------
FACT_KEYS: dict[str, tuple[str, str]] = {
    # --- BEP: what was approved (BRD 1.1) ----------------------------------
    "bep.customer_name":            ("BEP", "Tên khách hàng trên hệ thống phê duyệt"),
    "bep.tax_code":                 ("BEP", "Mã số thuế"),
    "bep.address":                  ("BEP", "Địa chỉ khách hàng"),
    "bep.owner_name":               ("BEP", "Tên chủ doanh nghiệp"),
    "bep.owner_id_number":          ("BEP", "Số CCCD của chủ doanh nghiệp"),
    "bep.owner_birth_year":         ("BEP", "Năm sinh của chủ doanh nghiệp"),
    "bep.gso_code":                 ("BEP", "Mã ngành GSO của khách hàng"),
    "bep.industry":                 ("BEP", "Tên ngành nghề của khách hàng trên BEP"),
    "bep.program":                  ("BEP", "Chương trình cấp tín dụng (B1CP/MISA/PLPP)"),
    "bep.approved_limit":           ("BEP", "Tổng HMTD được phê duyệt, đồng"),
    "bep.approved_limit_by_product":("BEP", "HMTD phê duyệt theo từng sản phẩm, đồng"),
    "bep.batch_valid_from":         ("BEP", "Ngày lô phê duyệt bắt đầu hiệu lực"),
    "bep.batch_valid_to":           ("BEP", "Ngày lô phê duyệt hết hiệu lực"),
    "bep.sto_revenue":              ("BEP", "Doanh thu STO trên BEP, đồng"),

    # --- T24: what was actually booked (BRD 2.3.c) -------------------------
    "t24.booking_date":             ("T24", "Ngày hạch toán HMTD"),
    "t24.active_limit":             ("T24", "Tổng HMTD đã active, đồng"),
    "t24.active_limit_by_product":  ("T24", "HMTD đã active theo từng sản phẩm, đồng"),
    "t24.ccr":                      ("T24", "CCR hạch toán trên BBC, phần trăm"),
    "cashflow.pdld_count":          ("T24", "Số lần phát sinh PDLD"),
    # Shape: [{"kind": str, "value": float}, ...]
    "collateral.items":             ("T24", "Danh sách TSBĐ trên hệ thống: loại và giá trị"),

    # --- BCDE: what the appraisal officer looked up and filed (BRD 2.3.b) --
    "cic.customer_debt_group_at_approval": ("BCDE", "Nhóm nợ của KH tại thời điểm phê duyệt"),
    "cic.owner_debt_group_at_approval":    ("BCDE", "Nhóm nợ của CDN tại thời điểm phê duyệt"),
    "blwl.customer_at_approval":           ("BCDE", "KH có trong BL/WL tại thời điểm phê duyệt"),
    "blwl.owner_at_approval":              ("BCDE", "CDN có trong BL/WL tại thời điểm phê duyệt"),

    # --- Fresh lookups filed with the dossier (BRD 2.4) --------------------
    "cic.customer_debt_group_at_postcheck": ("Tài liệu", "Nhóm nợ của KH tại thời điểm post-check"),
    "cic.owner_debt_group_at_postcheck":    ("Tài liệu", "Nhóm nợ của CDN tại thời điểm post-check"),
    "blwl.customer_at_postcheck":           ("Tài liệu", "KH có trong BL/WL tại thời điểm post-check"),
    "blwl.owner_at_postcheck":              ("Tài liệu", "CDN có trong BL/WL tại thời điểm post-check"),

    # --- Third party: Virac is the only one (BRD 2.4) ----------------------
    "virac.revenue_by_year":        ("Virac", "Doanh thu theo năm, đồng"),
    "virac.net_profit_by_year":     ("Virac", "Lợi nhuận sau thuế theo năm, đồng"),

    # --- Dossier: identity read off the documents (BRD 1.1) ----------------
    # One fact per field rather than a single blob. If they were bundled, a
    # rule comparing "customer name" would run over an empty list and report a
    # pass when no document carried a name at all. Split, the runner's
    # missing-data gate covers the field level for free.
    # Shape: [{"filename": str, "value": Any}, ...]
    "doc.customer_name_values":     ("Tài liệu", "Tên KH đọc được trên từng chứng từ"),
    "doc.tax_code_values":          ("Tài liệu", "Mã số thuế đọc được trên từng chứng từ"),
    "doc.address_values":           ("Tài liệu", "Địa chỉ đọc được trên từng chứng từ"),
    "doc.owner_name_values":        ("Tài liệu", "Tên chủ doanh nghiệp đọc được trên từng chứng từ"),
    "doc.owner_id_number_values":   ("Tài liệu", "Số CCCD đọc được trên từng chứng từ"),
    "doc.owner_birth_year_values":  ("Tài liệu", "Năm sinh CDN đọc được trên từng chứng từ"),
    "doc.document_date_values":     ("Tài liệu", "Ngày ghi trên từng chứng từ"),
    "doc.document_number_values":   ("Tài liệu", "Số hiệu ghi trên từng chứng từ"),
    # Shape: [{"filename": str, "type_id": str, "has_signature": bool, "has_seal": bool}, ...]
    "doc.signature_and_seal":       ("Tài liệu", "Tình trạng chữ ký và con dấu của từng chứng từ"),
    "doc.types_present":            ("Tài liệu", "Các đầu mục hồ sơ nhận diện được theo tên file"),
    "doc.extensions":               ("Tài liệu", "Định dạng của từng file trong hồ sơ"),
    "doc.industry_on_registration": ("Tài liệu", "Ngành nghề ghi trên giấy đăng ký kinh doanh"),
    "doc.industry_on_sitevisit":    ("Tài liệu", "Ngành nghề ĐVKD ghi nhận khi khảo sát thực địa"),

    # --- Dossier: financial statements -------------------------------------
    "doc.financials.report_year":            ("Tài liệu", "Năm của kỳ báo cáo tài chính"),
    "doc.financials.total_assets":           ("Tài liệu", "Tổng tài sản trên BCTC, đồng"),
    "doc.financials.total_capital":          ("Tài liệu", "Tổng nguồn vốn trên BCTC, đồng"),
    "doc.financials.revenue_prior_year":     ("Tài liệu", "Doanh thu kỳ trước trên BCTC, đồng"),
    "doc.financials.revenue_current_year":   ("Tài liệu", "Doanh thu kỳ báo cáo trên BCTC, đồng"),
    "doc.financials.net_profit_current_year":("Tài liệu", "Lợi nhuận sau thuế kỳ báo cáo trên BCTC, đồng"),
    "doc.financials.has_digital_signature":  ("Tài liệu", "BCTC có chữ ký điện tử"),

    # Shape: [{"lender", "kind", "description", "value", "released_on"}, ...]
    "cic.collateral_items":         ("Tài liệu", "TSBĐ đăng ký tại CIC theo báo cáo R20"),

    # --- Dossier: credit application ---------------------------------------
    "doc.proposal.declared_revenue":("Tài liệu", "Doanh thu khách hàng kê khai trên Đề nghị vay vốn, đồng"),
    "doc.proposal.requested_limit": ("Tài liệu", "Tổng HMTD khách hàng đề nghị, đồng"),
    "doc.proposal.collateral_items":("Tài liệu", "TSBĐ khách hàng kê trong Đề nghị vay vốn"),

    # --- The review itself --------------------------------------------------
    "case.postcheck_date":          ("Hồ sơ", "Ngày thực hiện rà soát post-check"),
}


# No extraction pass reads these fields, and this version deliberately does not
# add one. Rules that need them always stop at INSUFFICIENT_DATA. Declared here
# so that "nobody collects this" is a stated decision rather than an oversight;
# `verify_manual_facts` asserts this set matches reality in both directions.
# The reason strings are Vietnamese: they are printed into the report appendix.
MANUAL_FACTS: dict[str, str] = {
    "doc.owner_id_number_values":            "chưa có nguồn trích xuất; điền thủ công hoặc bổ sung pass",
    "doc.owner_birth_year_values":           "chưa có nguồn trích xuất; điền thủ công hoặc bổ sung pass",
    "doc.industry_on_registration":          "chưa có pass đọc giấy đăng ký kinh doanh",
    "doc.document_number_values":            "chưa có nguồn trích xuất số hiệu chứng từ",
    "doc.signature_and_seal":                "chưa có pass nhận diện chữ ký và con dấu",
    "doc.financials.has_digital_signature":  "chưa có pass nhận diện chữ ký điện tử trên BCTC",
    "blwl.customer_at_postcheck":            "chưa có pass đọc file BL/WL tra cứu tại thời điểm post-check",
    "blwl.owner_at_postcheck":               "chưa có pass đọc file BL/WL tra cứu tại thời điểm post-check",
}


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

        _, description = FACT_KEYS.get(path, ("", path))
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
