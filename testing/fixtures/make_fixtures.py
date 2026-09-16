"""Regenerate the rule fixtures. Run: python3 testing/fixtures/make_fixtures.py

Three shapes, each catching a different failure:
  case_clean          - every rule passes. Catches a rule that can never pass.
  case_broken         - every rule fails except P01. Catches a rule that cannot
                        detect its own violation.
  case_broken_program - an unknown program, so P01 has a violation of its own.
  (case_blank is not a file: the gate test builds it as an empty Facts.)

Fixtures set facts directly, so the whole rule suite is testable with no LLM
and no database - including the facts that have no collector in production.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BILLION = 10 ** 9

SIGNED_TYPES = [
    "giay_dang_ky_kinh_doanh",
    "bang_can_doi_ke_toan",
    "bao_cao_ket_qua_kinh_doanh",
    "de_nghi_cap_tin_dung",
    "bao_cao_khao_sat_thuc_dia",
]
B1CP_REQUIRED = SIGNED_TYPES + [
    "to_khai_thue_gtgt",
    "cic_khach_hang_vay",
    "cic_dai_dien_phap_luat_co_dong",
]

CLEAN_FILES = ["dkkd.pdf", "bctc_2023.pdf", "de_nghi_vay_von.docx", "cic_kh.pdf"]


def _values(filenames, value):
    return [{"filename": name, "value": value} for name in filenames]


def clean() -> dict:
    return {
        # --- BEP ---
        "bep.customer_name": "CÔNG TY TNHH THƯƠNG MẠI ABC",
        "bep.tax_code": "0101234567",
        "bep.address": "Số 10, P. Láng Hạ, Q. Đống Đa, TP. Hà Nội",
        "bep.owner_name": "Nguyễn Văn A",
        "bep.owner_id_number": "001080001234",
        "bep.owner_birth_year": 1980,
        "bep.gso_code": "4610",
        "bep.industry": "Bán buôn tổng hợp",
        "bep.program": "B1CP",
        "bep.approved_limit": 5 * BILLION,
        "bep.approved_limit_by_product": {"Vay ngắn hạn": 3 * BILLION, "Thấu chi": 2 * BILLION},
        "bep.batch_valid_from": "2025-01-02",
        "bep.batch_valid_to": "2025-06-30",
        "bep.sto_revenue": 20 * BILLION,
        # --- T24 ---
        "t24.booking_date": "2025-03-14",     # before 30/04 -> statements must be N-2 = 2023
        "t24.active_limit": 5 * BILLION,
        "t24.active_limit_by_product": {"Vay ngắn hạn": 3 * BILLION, "Thấu chi": 2 * BILLION},
        "t24.ccr": 70,
        "collateral.items": [{"kind": "BDS", "value": 8 * BILLION}],
        # --- BCDE ---
        "cic.customer_debt_group_at_approval": 1,
        "cic.owner_debt_group_at_approval": 1,
        "blwl.customer_at_approval": False,
        "blwl.owner_at_approval": False,
        # --- Fresh lookups filed with the dossier ---
        "cic.customer_debt_group_at_postcheck": 1,
        "cic.owner_debt_group_at_postcheck": 1,
        "blwl.customer_at_postcheck": False,
        "blwl.owner_at_postcheck": False,
        # --- Third parties ---
        "virac.revenue_by_year": {"2023": 21 * BILLION},
        "virac.net_profit_by_year": {"2023": int(1.5 * BILLION)},
        "cashflow.pdld_count": 5,
        # --- Dossier: identity ---
        "doc.customer_name_values": _values(CLEAN_FILES, "Công ty TNHH Thương mại ABC"),
        "doc.tax_code_values": _values(CLEAN_FILES, "0101234567"),
        "doc.address_values": _values(["cic_kh.pdf"],
                                      "Số 10, Phường Láng Hạ, Quận Đống Đa, Thành phố Hà Nội"),
        "doc.owner_name_values": _values(["cic_kh.pdf"], "NGUYỄN VĂN A"),
        "doc.owner_id_number_values": _values(["dkkd.pdf"], "001 080 001234"),
        "doc.owner_birth_year_values": _values(["dkkd.pdf"], "01/01/1980"),
        "doc.document_date_values": [
            {"filename": "cic_kh.pdf", "value": "2024-12-20"},
            {"filename": "khao_sat.pdf", "value": "2024-12-15"},
        ],
        "doc.document_number_values": [
            {"filename": name, "value": f"SH-{index:03d}/2024"}
            for index, name in enumerate(CLEAN_FILES, start=1)
        ],
        "doc.signature_and_seal": [
            {"filename": f"{type_id}.pdf", "type_id": type_id,
             "has_signature": True, "has_seal": True}
            for type_id in SIGNED_TYPES
        ],
        "doc.types_present": B1CP_REQUIRED,
        "doc.extensions": [
            {"filename": name, "extension": "." + name.rsplit(".", 1)[1]}
            for name in CLEAN_FILES
        ],
        "doc.industry_on_registration": "Bán buôn tổng hợp",
        "doc.industry_on_sitevisit": "Bán buôn tổng hợp, kho hàng tại Hà Nội",
        # --- Dossier: financial statements ---
        "doc.financials.report_year": 2023,
        "doc.financials.total_assets": 12 * BILLION,
        "doc.financials.total_capital": 12 * BILLION,
        "doc.financials.revenue_prior_year": 18 * BILLION,
        "doc.financials.revenue_current_year": 22 * BILLION,
        "doc.financials.net_profit_current_year": int(1.4 * BILLION),
        "doc.financials.has_digital_signature": True,
        # --- Dossier: credit application ---
        "doc.proposal.declared_revenue": 22 * BILLION,
        "doc.proposal.requested_limit": 5 * BILLION,
        "doc.proposal.collateral_items": [
            {"category": "BDS", "description": "Nhà xưởng Hà Nội", "value": 8 * BILLION}
        ],
        "cic.collateral_items": [
            {"lender": "TCB - CN Hà Nội", "kind": "01",
             "description": "Nhà xưởng Hà Nội", "value": 8 * BILLION,
             "released_on": None}
        ],
        # --- The review ---
        "case.postcheck_date": "2025-09-14",
    }


def broken() -> dict:
    """Every rule violated except P01, whose program stays valid so the rest run."""

    files = ["dkkd.pdf", "bctc_2022.pdf", "anh_kho.jpg"]
    data = clean()
    data.update({
        # V01..V06: documents disagree with BEP, and with each other -> F01 too
        "doc.customer_name_values": [
            {"filename": "dkkd.pdf", "value": "Công ty TNHH Thương mại ABD"},
            {"filename": "bctc_2022.pdf", "value": "Công ty CP Thương mại ABC"},
        ],
        "doc.tax_code_values": [
            {"filename": "dkkd.pdf", "value": "0101234567"},
            {"filename": "bctc_2022.pdf", "value": "0109999999"},
        ],
        "doc.address_values": [
            {"filename": "dkkd.pdf", "value": "Số 10, P. Láng Hạ, Q. Đống Đa, TP. Hà Nội"},
            {"filename": "bctc_2022.pdf", "value": "Số 99, P. Trung Hoà, Q. Cầu Giấy, TP. Hà Nội"},
        ],
        "doc.owner_name_values": [
            {"filename": "dkkd.pdf", "value": "Nguyễn Văn A"},
            {"filename": "bctc_2022.pdf", "value": "Trần Thị B"},
        ],
        "doc.owner_id_number_values": _values(files, "001080009999"),
        "doc.owner_birth_year_values": _values(files, "1975"),
        # V07
        "doc.industry_on_registration": "Kinh doanh bất động sản",
        "doc.industry_on_sitevisit": "Cho thuê kho bãi",
        # F02: a document dated after the approval, and a reused document number
        "doc.document_date_values": [
            {"filename": "dkkd.pdf", "value": "2025-05-10"},
            {"filename": "bctc_2022.pdf", "value": "2024-03-30"},
        ],
        "doc.document_number_values": [
            {"filename": "dkkd.pdf", "value": "SH-001/2024"},
            {"filename": "bctc_2022.pdf", "value": "SH-001/2024"},
        ],
        # P02: mandatory items absent
        "doc.types_present": ["giay_dang_ky_kinh_doanh", "bang_can_doi_ke_toan"],
        # P03: a disallowed format
        "doc.extensions": [
            {"filename": "dkkd.pdf", "extension": ".pdf"},
            {"filename": "anh_kho.jpg", "extension": ".jpg"},
        ],
        # P04: seal missing
        "doc.signature_and_seal": [
            {"filename": f"{type_id}.pdf", "type_id": type_id,
             "has_signature": True, "has_seal": False}
            for type_id in SIGNED_TYPES
        ],
        # P05, P06
        "doc.financials.has_digital_signature": False,
        "doc.financials.total_assets": 12 * BILLION,
        "doc.financials.total_capital": 11 * BILLION,
        # O01: booked after the approval expired. P07 follows: from 30/04 the
        # statements must be 2024, and the dossier files 2022.
        "t24.booking_date": "2025-08-15",
        "doc.financials.report_year": 2022,
        # O02: over the approved limit
        "t24.active_limit": 8 * BILLION,
        "t24.active_limit_by_product": {"Vay ngắn hạn": 6 * BILLION, "Thấu chi": 2 * BILLION},
        # C01 non-core industry; C02 debt group over; C03 listed;
        # O03 not unsecured-eligible yet CCR below 100; O04 wrong collateral kind
        "bep.gso_code": "4711",
        "t24.ccr": 50,
        "cic.customer_debt_group_at_approval": 3,
        "cic.owner_debt_group_at_approval": 2,
        "blwl.customer_at_approval": True,
        "collateral.items": [{"kind": "HANG TON KHO", "value": 4 * BILLION}],
        # O05: approved more than requested
        "doc.proposal.requested_limit": 2 * BILLION,
        # O07: every asset on CIC has been released, so nothing secures the
        # facility any more. O08: 0 pledged at CIC against 4bn on the system.
        "cic.collateral_items": [
            {"lender": "TCB - CN Hà Nội", "kind": "01",
             "description": "Nhà xưởng Hà Nội", "value": 8 * BILLION,
             "released_on": "12/03/2025"}
        ],
        # O06: dossier collateral disagrees with the system
        "doc.proposal.collateral_items": [
            {"category": "HANG TON KHO", "description": "Kho hàng", "value": 1 * BILLION}
        ],
        # E01, E02
        "cic.customer_debt_group_at_postcheck": 3,
        "cic.owner_debt_group_at_postcheck": 2,
        "blwl.customer_at_postcheck": True,
        "blwl.owner_at_postcheck": True,
        # E03: STO 20bn against 2bn declared -> 90%
        "doc.proposal.declared_revenue": 2 * BILLION,
        # E04: same period 2022, far apart
        "virac.revenue_by_year": {"2022": 50 * BILLION},
        "virac.net_profit_by_year": {"2022": 9 * BILLION},
        "doc.financials.revenue_current_year": 22 * BILLION,
        "doc.financials.net_profit_current_year": int(1.4 * BILLION),
        # E05: 5bn -> 22bn is 77%
        "doc.financials.revenue_prior_year": 5 * BILLION,
        # E06
        "cashflow.pdld_count": 0,
    })
    return data


def broken_program() -> dict:
    """Exists so P01 has a violation: BEP returns a program nobody declared."""

    data = clean()
    data["bep.program"] = "CHUONG_TRINH_LA"
    return data


def main() -> None:
    here = Path(__file__).parent
    for name, builder in (
        ("case_clean", clean),
        ("case_broken", broken),
        ("case_broken_program", broken_program),
    ):
        payload = {"values": builder(), "reasons": {}}
        path = here / f"{name}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {path.relative_to(ROOT)} ({len(payload['values'])} facts)")


if __name__ == "__main__":
    main()
