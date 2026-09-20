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
B1CP_REQUIRED = SIGNED_TYPES + ["to_khai_thue_gtgt", "anh_khao_sat_thuc_dia"]

CLEAN_FILES = ["dkkd.pdf", "bctc_2023.pdf", "de_nghi_vay_von.docx", "khao_sat.pdf"]


def _values(filenames, value):
    return [{"filename": name, "value": value} for name in filenames]


def clean() -> dict:
    return {
        # --- LOS ---
        "los.customer_name": "CÔNG TY TNHH THƯƠNG MẠI ABC",
        "los.tax_code": "0101234567",
        "los.address": "Số 10, P. Láng Hạ, Q. Đống Đa, TP. Hà Nội",
        "los.owner_name": "Nguyễn Văn A",
        "los.owner_id_number": "001080001234",
        "los.owner_birth_year": 1980,
        # In config/programs.yaml's focus_GSO, so C01 does not force CCR to 100%.
        "los.gso_code": "4711",
        "los.industry": "Bán lẻ tổng hợp",
        "los.persona": "Thương mại",
        "los.is_site_visit": True,
        "los.program": "B1CP",
        "los.approved_limit": 5 * BILLION,
        "los.approved_limit_by_product": {"Vay ngắn hạn": 3 * BILLION, "Thấu chi": 2 * BILLION},
        "los.batch_valid_from": "2025-01-02",
        "los.batch_valid_to": "2025-06-30",
        "los.sto_revenue": 20 * BILLION,
        "los.chief_accountant_name": "Lê Thị Kế Toán",
        "los.shareholders": [
            {"name": "Nguyễn Văn A", "id_number": "001080001234", "stake_pct": 60.0},
            {"name": "Đỗ Thị Hạnh", "id_number": "001082007777", "stake_pct": 40.0},
        ],
        # What the RM keyed into LOS, agreeing with the documents (V08, V09).
        "los.sitevisit_online.industry": "Bán lẻ tổng hợp",
        "los.sitevisit_online.address":
            "Số 10, Phường Láng Hạ, Quận Đống Đa, Thành phố Hà Nội",
        "los.financials_online.report_year": 2023,
        "los.financials_online.report_type": "Báo cáo thuế",
        "los.financials_online.revenue": 20 * BILLION,
        "los.financials_online.net_profit": int(1.4 * BILLION),
        # --- T24 ---
        "t24.booking_date": "2025-03-14",     # before 30/04 -> statements must be N-2 = 2023
        "t24.active_limit": 5 * BILLION,
        "t24.active_limit_by_product": {"Vay ngắn hạn": 3 * BILLION, "Thấu chi": 2 * BILLION},
        "t24.outstanding": 4 * BILLION,
        # Collected and printed, graded by nothing - see DISPLAY_ONLY_FACTS.
        "t24.transactions_by_period": [
            {"ky": "2025-04", "ghi_no": int(4.2 * BILLION), "ghi_co": int(4.4 * BILLION),
             "so_du_binh_quan": int(1.1 * BILLION), "so_luong_gd": 142},
        ],
        "portfolio.facilities": [
            {"san_pham": "Vay ngắn hạn", "so_hop_dong": "HD2025/001",
             "du_no": int(2.5 * BILLION), "nhom_no": 1},
        ],
        "t24.ccr": 70,
        "collateral.items": [{"kind": "BDS", "value": 8 * BILLION}],
        # --- CIC and BL/WL at the approval date ---
        "cic.customer_debt_group_at_approval": 1,
        "cic.owner_debt_group_at_approval": 1,
        "blwl.customer_at_approval": False,
        "blwl.owner_at_approval": False,
        "blwl.shareholders_at_approval": {"Nguyễn Văn A": False, "Đỗ Thị Hạnh": False},
        "amc.customer_at_approval": False,
        "amc.owner_at_approval": False,
        "amc.shareholders_at_approval": {"Nguyễn Văn A": False, "Đỗ Thị Hạnh": False},
        "cic.shareholder_debt_groups_at_approval": {"Nguyễn Văn A": 1, "Đỗ Thị Hạnh": 1},
        # --- CIC and BL/WL at the review date ---
        "cic.customer_debt_group_at_postcheck": 1,
        "cic.owner_debt_group_at_postcheck": 1,
        "blwl.customer_at_postcheck": False,
        "blwl.owner_at_postcheck": False,
        "blwl.shareholders_at_postcheck": {"Nguyễn Văn A": False, "Đỗ Thị Hạnh": False},
        "amc.customer_at_postcheck": False,
        "amc.owner_at_postcheck": False,
        "amc.shareholders_at_postcheck": {"Nguyễn Văn A": False, "Đỗ Thị Hạnh": False},
        "cic.shareholder_debt_groups_at_postcheck": {"Nguyễn Văn A": 1, "Đỗ Thị Hạnh": 1},
        # --- Third parties ---
        # E04 expects Virac and the statements to be EQUAL for the same period.
        "virac.revenue_by_year": {"2023": 22 * BILLION},
        "virac.net_profit_by_year": {"2023": int(1.4 * BILLION)},
        "cashflow.pdld_count": 0,
        # --- Dossier: identity ---
        "doc.customer_name_values": _values(CLEAN_FILES, "Công ty TNHH Thương mại ABC"),
        "doc.tax_code_values": _values(CLEAN_FILES, "0101234567"),
        "doc.address_values": _values(["khao_sat.pdf"],
                                      "Số 10, Phường Láng Hạ, Quận Đống Đa, Thành phố Hà Nội"),
        "doc.owner_name_values": _values(["khao_sat.pdf"], "NGUYỄN VĂN A"),
        "doc.owner_id_number_values": _values(["dkkd.pdf"], "001 080 001234"),
        "doc.owner_birth_year_values": _values(["dkkd.pdf"], "01/01/1980"),
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
        "doc.industry_on_registration": "Bán lẻ tổng hợp",
        "doc.industry_on_sitevisit": "Bán lẻ tổng hợp, kho hàng tại Hà Nội",
        # V10: the trade persona needs 1 of its markers; two photos show two.
        "doc.sitevisit_photo_evidence": [
            {"filename": "anh_khao_sat_thuc_dia_1.jpg",
             "markers": ["cua hang", "hang hoa tren ke"],
             "note": "Mặt tiền cửa hàng, hàng bày trên kệ"},
            {"filename": "anh_khao_sat_thuc_dia_2.jpg",
             "markers": ["kho hang"], "note": "Kho phía sau cửa hàng"},
        ],
        # --- Dossier: financial statements ---
        "doc.financials.report_year": 2023,
        "doc.financials.report_type": "Báo cáo thuế",
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
        # V01..V06: documents disagree with LOS, and with each other -> F01 too
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
        # P02: mandatory items absent
        "doc.types_present": ["giay_dang_ky_kinh_doanh", "bang_can_doi_ke_toan"],
        # P03: a disallowed format. Images are allowed now - site-visit photos
        # arrive as .jpg - so the violation is an archive, which no reader opens
        # and which hides whatever is inside it from every criterion.
        "doc.extensions": [
            {"filename": "dkkd.pdf", "extension": ".pdf"},
            {"filename": "anh_kho.jpg", "extension": ".jpg"},
            {"filename": "ho_so_goc.zip", "extension": ".zip"},
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
        "doc.financials.report_type": "Báo cáo thuế",
        # O02: over the approved limit
        "t24.active_limit": 8 * BILLION,
        "t24.active_limit_by_product": {"Vay ngắn hạn": 6 * BILLION, "Thấu chi": 2 * BILLION},
        # C01 off-focus industry; C02 debt group over; C03 listed;
        # O03 not unsecured-eligible yet CCR below 100; O04 wrong collateral kind
        "los.gso_code": "4610",
        "t24.ccr": 50,
        "cic.customer_debt_group_at_approval": 3,
        "cic.owner_debt_group_at_approval": 2,
        "blwl.customer_at_approval": True,
        # C05, E07: in a recovery workflow at both moments
        "amc.customer_at_approval": True,
        "amc.owner_at_approval": False,
        "amc.customer_at_postcheck": True,
        "amc.owner_at_postcheck": False,
        # C06, E08: one shareholder on a list, one over the debt-group threshold
        "blwl.shareholders_at_approval": {"Nguyễn Văn A": True, "Đỗ Thị Hạnh": False},
        "amc.shareholders_at_approval": {"Nguyễn Văn A": False, "Đỗ Thị Hạnh": True},
        "cic.shareholder_debt_groups_at_approval": {"Nguyễn Văn A": 3, "Đỗ Thị Hạnh": 1},
        "blwl.shareholders_at_postcheck": {"Nguyễn Văn A": True, "Đỗ Thị Hạnh": False},
        "amc.shareholders_at_postcheck": {"Nguyễn Văn A": False, "Đỗ Thị Hạnh": True},
        "cic.shareholder_debt_groups_at_postcheck": {"Nguyễn Văn A": 4, "Đỗ Thị Hạnh": 1},
        # V10: the manufacturing persona needs 2 markers; the photos show none
        "los.persona": "Sản xuất",
        "los.is_site_visit": True,
        "doc.sitevisit_photo_evidence": [
            {"filename": "anh_1.jpg", "markers": ["van phong"],
             "note": "Một phòng làm việc, không thấy xưởng hay máy móc"},
        ],
        # V08: the RM keyed an industry the documents contradict
        "los.sitevisit_online.industry": "Cho thuê kho bãi",
        "los.sitevisit_online.address": "Số 99, Phường Khác, Quận Khác, Thành phố Hà Nội",
        # V09: a different period AND a different kind of report from the one filed
        "los.financials_online.report_year": 2023,
        "los.financials_online.report_type": "Báo cáo kiểm toán",
        "los.financials_online.revenue": 5 * BILLION,
        "los.financials_online.net_profit": 100_000_000,
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
        # E06: three overdue LDs against a ceiling of zero
        "cashflow.pdld_count": 3,
    })
    return data


def broken_program() -> dict:
    """Exists so P01 has a violation: LOS returns a program nobody declared."""

    data = clean()
    data["los.program"] = "CHUONG_TRINH_LA"
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
