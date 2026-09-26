"""Build a SQLite database shaped like the systems the tools query.

Why this exists: every SQL statement under src/tools/ is a guess at a view that
lives in production, and until the run happens there nothing proves the names
line up or that the pipeline writes each returned column into the right fact.
This dataset lets the whole review run end to end - queries included - with no
database access and no LLM call, which is what testing/checks/verify_dummy_db.py
grades.

The table names and column names here are NOT the real ones. They mirror
whatever the tools' SQL currently says, so when the real view names arrive, this
file changes alongside the SQL and the check keeps holding.

Two customers:

  0201123795  the customer in samples/case_demo. Every figure agrees with the
              documents in that dossier, so a full run reports Đạt. That
              agreement is the point - it is what shows each query result
              reaching the fact the rules read.
  0209999999  the same shape with the numbers pushed out of tolerance, so the
              failing half of every rule is reachable too.

All data is invented. No customer, company, or credit file here is real.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils.pii import IDENTIFIER, NAME, pii_hash  # noqa: E402
DEFAULT_PATH = Path(__file__).resolve().parent / "postcheck_dummy.sqlite"

BILLION = 1_000_000_000

# The dossier in samples/case_demo -------------------------------------------
OK = "0201123795"
# Approval window, and a booking date inside it. The booking date also decides
# which financial year the statements must cover (P07): on or after 30/04 the
# review wants year N-1, and the dossier carries 2025, so the date sits in 2026.
OK_VALID_FROM = "2026-04-01"
OK_VALID_TO = "2026-09-30"
OK_BOOKED = "2026-05-04"

# The same shape, out of tolerance -------------------------------------------
BAD = "0209999999"

SCHEMA: dict[str, tuple[str, ...]] = {
    # LOS holds four kinds of information about a file, and they are four tables
    # here for the same reason they are four tools: different grain, different use.
    # One row per product, file-level fields repeated - the same shape as
    # v_t24_han_muc, which is what these limits are compared against.
    "v_los_phe_duyet": (
        "mst", "ten_kh", "dia_chi", "ten_cdn", "cccd_cdn", "nam_sinh_cdn",
        "ten_ke_toan_truong",
        "ma_gso", "nganh_nghe", "chan_dung", "co_khao_sat_thuc_dia", "chuong_trinh",
        "hmtd_phe_duyet", "san_pham", "hmtd_phe_duyet_san_pham", "dt_sto",
        "batch_hieu_luc_tu", "batch_het_hieu_luc",
    ),
    "v_los_co_dong": ("mst", "ten", "so_cccd", "ty_le"),
    "v_los_khao_sat_online": ("mst", "nganh_nghe", "dia_chi", "ngay_khao_sat"),
    "v_los_bctc_online": ("mst", "nam", "loai_bao_cao", "doanh_thu", "lnst"),
    "v_t24_han_muc": ("mst", "san_pham", "hmtd_active", "ngay_hach_toan", "ccr"),
    "v_du_no": ("mst", "du_no"),
    "v_tai_san_dam_bao": ("mst", "loai", "gia_tri"),
    "v_giao_dich_pdld": ("mst", "ngay_giao_dich"),
    "v_t24_giao_dich_tong_hop": (
        "mst", "ky", "ghi_no", "ghi_co", "so_du_binh_quan", "so_luong_gd",
    ),
    "v_cic_nhom_no": ("mst", "doi_tuong", "nhom_no", "ngay_tra_cuu"),
    # Shareholders are people: looked up by national ID, not by the company's tax code.
    "v_cic_nhom_no_ca_nhan": ("so_cccd", "nhom_no", "ngay_tra_cuu"),
    "v_cic_tai_san_dam_bao": (
        "mst", "tctd", "loai_tai_san", "mo_ta_tai_san", "gia_tri", "ngay_giai_chap",
    ),
    # The list itself, not a per-customer flag: an entry names a company by tax
    # code or a person by national ID, and is in force between ngay_vao and
    # ngay_ra (NULL = still listed).
    "v_danh_sach_black_warning_list": (
        "loai_danh_sach", "mst", "so_cccd", "ten", "ly_do", "ngay_vao", "ngay_ra",
    ),
    "v_danh_sach_amc": ("mst", "so_cccd", "ten", "ly_do", "ngay_vao", "ngay_ra"),
    "v_danh_muc_tin_dung": (
        "mst", "san_pham", "so_hop_dong", "du_no", "ngay_giai_ngan",
        "ngay_dao_han", "nhom_no",
    ),
    "v_virac_tai_chinh": ("mst", "nam", "doanh_thu", "lnst"),
}

# PRODUCTION HASHES ITS PII COLUMNS, so this database must too - otherwise the
# checks grade a shape of data that does not exist. The rows below are written in
# plaintext for readability and hashed on the way in.
PII_COLUMNS: dict[str, dict[str, str]] = {
    "v_los_phe_duyet": {"ten_cdn": NAME, "cccd_cdn": IDENTIFIER,
                        "ten_ke_toan_truong": NAME},
    "v_los_co_dong": {"ten": NAME, "so_cccd": IDENTIFIER},
    "v_cic_nhom_no_ca_nhan": {"so_cccd": IDENTIFIER},
    "v_danh_sach_black_warning_list": {"so_cccd": IDENTIFIER, "ten": NAME},
    "v_danh_sach_amc": {"so_cccd": IDENTIFIER, "ten": NAME},
}

ROWS: dict[str, list[tuple]] = {
    "v_los_phe_duyet": [
        # Two products, so every file-level field repeats. hmtd_phe_duyet is the
        # file TOTAL (5bn); the products split it 3 + 2.
        (OK, "CÔNG TY CỔ PHẦN XÂY DỰNG - THƯƠNG MẠI KIM HẢI",
         "Số 10, P. Láng Hạ, Q. Đống Đa, TP. Hà Nội",
         "Nguyễn Văn A", "001080001234", 1980,
         "Lê Thị Kế Toán",
         # Construction, which is not in config's focus_GSO stub - so C01 requires
         # CCR 100%, and the CCR below is 100%.
         "4290", "Xây dựng công trình dân dụng và thương mại",
         "Sản xuất", 1, "B1CP",
         5 * BILLION, "Vay ngắn hạn", 3 * BILLION, 62 * BILLION,
         OK_VALID_FROM, OK_VALID_TO),
        (OK, "CÔNG TY CỔ PHẦN XÂY DỰNG - THƯƠNG MẠI KIM HẢI",
         "Số 10, P. Láng Hạ, Q. Đống Đa, TP. Hà Nội",
         "Nguyễn Văn A", "001080001234", 1980,
         "Lê Thị Kế Toán",
         "4290", "Xây dựng công trình dân dụng và thương mại",
         "Sản xuất", 1, "B1CP",
         5 * BILLION, "Thấu chi", 2 * BILLION, 62 * BILLION,
         OK_VALID_FROM, OK_VALID_TO),
        (BAD, "CÔNG TY TNHH THƯƠNG MẠI BÌNH MINH",
         "Số 25, P. Trung Hoà, Q. Cầu Giấy, TP. Hà Nội",
         "Trần Thị B", "001185004321", 1985,
         "Phạm Văn Sổ Sách",
         # No site visit required, so V10 passes without looking at any photo.
         "4711", "Bán lẻ tổng hợp", "Thương mại", 0, "MISA",
         4 * BILLION, "Vay ngắn hạn", 4 * BILLION, 30 * BILLION,
         "2026-01-05", "2026-03-31"),
    ],
    "v_los_co_dong": [
        # Above the 30% the BRD singles out, and clean on every list.
        (OK, "Nguyễn Văn A", "001080001234", 55.0),
        (OK, "Đỗ Thị Hạnh", "001082007777", 30.0),
        (OK, "Vũ Minh Quân", "001090003333", 15.0),
        # One shareholder in the WL and one in recovery, so C06 and E08 have
        # something to catch that the KH/CDN rules would miss.
        (BAD, "Trần Thị B", "001185004321", 60.0),
        (BAD, "Hoàng Văn Nợ", "001177008888", 40.0),
    ],
    "v_los_khao_sat_online": [
        # What the RM keyed in. Matches the site visit report in samples/case_demo.
        (OK, "Xây dựng công trình dân dụng và thương mại",
         "Số 10, P. Láng Hạ, Q. Đống Đa, TP. Hà Nội", "2026-03-20"),
        # Keyed an industry and an address the paperwork does not support (V08).
        (BAD, "Cho thuê kho bãi", "Số 99, P. Khác, Q. Khác, TP. Hà Nội", "2026-01-02"),
    ],
    "v_los_bctc_online": [
        # Within 40% of the e-tax filing in the dossier: DT 62.1 tỷ, LNST 382 triệu.
        # Same period and same kind as the e-tax filing in the dossier, so V09
        # passes; E03 compares this revenue against the STO figure on the file.
        (OK, 2025, "Báo cáo thuế", 61 * BILLION, 390_000_000),
        (OK, 2024, "Báo cáo thuế", 71 * BILLION, 350_000_000),
        # A different kind of report from the one filed, so V09 catches it.
        (BAD, 2025, "Báo cáo kiểm toán", 20 * BILLION, 100_000_000),
    ],
    "v_t24_han_muc": [
        (OK, "Vay ngắn hạn", 3 * BILLION, OK_BOOKED, 100),
        (OK, "Thấu chi", 2 * BILLION, OK_BOOKED, 100),
        # Booked after the approval expired (O01), over the approved limit (O02),
        # and at a CCR the criteria do not allow (O03).
        (BAD, "Vay ngắn hạn", 6 * BILLION, "2026-06-20", 50),
    ],
    "v_du_no": [
        (OK, int(3.2 * BILLION)),
        (BAD, int(5.8 * BILLION)),
    ],
    "v_tai_san_dam_bao": [
        (OK, "BĐS", 8 * BILLION),
        # Inventory cannot secure a facility booked below CCR 100% (O04).
        (BAD, "HÀNG TỒN KHO", 4 * BILLION),
    ],
    "v_giao_dich_pdld": [
        # Nothing for OK: no overdue LD is the passing state for E06.
        (BAD, "2026-05-11"),
        (BAD, "2026-06-02"),
        # BEFORE the approval date, so the window in CASHFLOW_PDLD_SQL must leave
        # it out. Without a row on the wrong side of the boundary, a query that
        # dropped its BETWEEN would still count 2 and look correct.
        (BAD, "2026-02-10"),
    ],
    "v_t24_giao_dich_tong_hop": [
        # Monthly rollups inside the review window, plus one month BEFORE the
        # approval date so the BETWEEN in TRANSACTION_SUMMARY_SQL has something to
        # exclude - without it the date clause could be dropped unnoticed.
        (OK, "2026-02", int(1.9 * BILLION), int(2.0 * BILLION), 900_000_000, 61),
        (OK, "2026-05", int(4.2 * BILLION), int(4.4 * BILLION), int(1.1 * BILLION), 142),
        (OK, "2026-06", int(3.8 * BILLION), int(4.1 * BILLION), int(1.2 * BILLION), 131),
        (OK, "2026-07", int(4.5 * BILLION), int(4.3 * BILLION), int(1.0 * BILLION), 155),
        (BAD, "2026-05", int(0.4 * BILLION), int(0.3 * BILLION), 60_000_000, 12),
        (BAD, "2026-07", int(0.2 * BILLION), int(0.1 * BILLION), 25_000_000, 5),
    ],
    "v_cic_nhom_no": [
        # One row per subject per lookup date. A subject with no row is UNKNOWN,
        # never group 1, which is why every subject appears at both dates.
        (OK, "KH", "Nợ đủ tiêu chuẩn", OK_VALID_FROM),
        (OK, "CDN", "Nợ đủ tiêu chuẩn", OK_VALID_FROM),
        (OK, "KH", "Nợ đủ tiêu chuẩn", "2026-09-10"),
        (OK, "CDN", "Nợ đủ tiêu chuẩn", "2026-09-10"),
        (BAD, "KH", "Nợ dưới tiêu chuẩn", "2026-01-05"),
        (BAD, "CDN", "Nợ cần chú ý", "2026-01-05"),
        (BAD, "KH", "Nợ nghi ngờ", "2026-09-10"),
        (BAD, "CDN", "Nợ cần chú ý", "2026-09-10"),
    ],
    "v_cic_nhom_no_ca_nhan": [
        ("001080001234", "Nợ đủ tiêu chuẩn", OK_VALID_FROM),
        ("001082007777", "Nợ đủ tiêu chuẩn", OK_VALID_FROM),
        ("001090003333", "Nợ đủ tiêu chuẩn", OK_VALID_FROM),
        ("001080001234", "Nợ đủ tiêu chuẩn", "2026-09-10"),
        ("001082007777", "Nợ đủ tiêu chuẩn", "2026-09-10"),
        ("001090003333", "Nợ đủ tiêu chuẩn", "2026-09-10"),
        ("001185004321", "Nợ cần chú ý", "2026-01-05"),
        ("001177008888", "Nợ dưới tiêu chuẩn", "2026-01-05"),
        ("001185004321", "Nợ nghi ngờ", "2026-09-10"),
        ("001177008888", "Nợ dưới tiêu chuẩn", "2026-09-10"),
    ],
    "v_cic_tai_san_dam_bao": [
        # No release date: still pledged, so it secures the facility (O07), and the
        # value matches what the systems hold (O08).
        (OK, "TCB - CN Hà Nội", "Bất động sản", "Nhà xưởng tại Hà Nội",
         8 * BILLION, None),
        # Released, so a facility booked below CCR 100% has nothing behind it.
        (BAD, "Ngân hàng A", "Hàng tồn kho", "Kho hàng Bình Minh",
         4 * BILLION, "2026-04-18"),
    ],
    "v_danh_sach_black_warning_list": [
        # Neither 0201123795 nor its owner appears, so that customer is clean at
        # both dates. The list is non-empty, which is what makes "clean" readable
        # as an answer rather than as a failed lookup.
        ("BL", BAD, None, "CÔNG TY TNHH THƯƠNG MẠI BÌNH MINH",
         "Gian lận chứng từ", "2025-11-30", None),
        # The owner of 0209999999, matched on the national ID, listed only from
        # mid-2026 - so the approval date is clean and the review date is not.
        ("WL", None, "001185004321", "Trần Thị B",
         "Liên quan vụ việc đang điều tra", "2026-07-01", None),
        # An entry that has been removed: in force before 2026-02-01 and not after,
        # so the as-of filter has something to exclude.
        ("WL", "0300000001", None, "CÔNG TY CỔ PHẦN AN PHÚ",
         "Chậm trả đã khắc phục", "2025-06-01", "2026-02-01"),
    ],
    "v_danh_sach_amc": [
        # The failing customer's company entered recovery before its approval, so
        # C05 catches it; the shareholder entered later, so E08 catches that and
        # C06 does not.
        (BAD, None, "CÔNG TY TNHH THƯƠNG MẠI BÌNH MINH",
         "Chuyển xử lý nợ", "2025-12-15", None),
        (None, "001177008888", "Hoàng Văn Nợ",
         "Đang thu hồi khoản vay cá nhân", "2026-06-10", None),
        # Closed before the approval date, so the as-of filter must exclude it.
        ("0300000002", None, "CÔNG TY TNHH CŨ",
         "Đã tất toán", "2025-03-01", "2026-01-20"),
    ],
    "v_danh_muc_tin_dung": [
        (OK, "Vay ngắn hạn", "HD2026/001", int(2.1 * BILLION),
         "2026-05-04", "2027-05-04", 1),
        (OK, "Thấu chi", "HD2026/002", int(1.1 * BILLION),
         "2026-05-04", "2027-05-04", 1),
        (BAD, "Vay ngắn hạn", "HD2026/101", int(5.8 * BILLION),
         "2026-06-20", "2027-06-20", 4),
    ],
    "v_virac_tai_chinh": [
        # E04 wants Virac and the filing to AGREE, so these are the e-tax figures
        # to the dong: DT 62,116,063,780 and LNST 382,284,650 for 2025.
        (OK, 2025, 62_116_063_780, 382_284_650),
        (OK, 2024, 71_176_996_993, 350_000_000),
        (BAD, 2025, 12 * BILLION, -500_000_000),
    ],
}


def hash_pii(table: str, columns: tuple[str, ...], row: tuple) -> tuple:
    """Replace each PII cell with the hash production stores in its place."""

    kinds = PII_COLUMNS.get(table, {})
    if not kinds:
        return row
    names = [column.split()[0] for column in columns]
    return tuple(
        pii_hash(value, kinds[name]) if name in kinds and value is not None else value
        for name, value in zip(names, row)
    )


def build(path: Path | str = DEFAULT_PATH) -> Path:
    """Create the database from scratch. Any existing file is replaced."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    with sqlite3.connect(target) as connection:
        for table, columns in SCHEMA.items():
            connection.execute(
                f"CREATE TABLE {table} ({', '.join(columns)})"
            )
            rows = [hash_pii(table, columns, row) for row in ROWS[table]]
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f"INSERT INTO {table} VALUES ({placeholders})", rows
            )
    return target


def main() -> None:
    target = build()
    print(f"wrote {target.relative_to(ROOT)}")
    for table in SCHEMA:
        print(f"    {table}: {len(ROWS[table])} row(s)")
    print(f"\nRun a review against it:\n"
          f"    from src.tools._executor import sqlite_executor\n"
          f"    Config(query_executor=sqlite_executor({str(target)!r}))")


if __name__ == "__main__":
    sys.exit(main())
