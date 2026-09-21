"""T24 - the core banking system. """
from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import one_row, rows


T24_FACILITIES_SQL = """
SELECT  san_pham, hmtd_active, ngay_hach_toan, ccr
FROM    v_t24_han_muc
WHERE   mst = :tax_code
ORDER   BY ngay_hach_toan
"""

COLLATERAL_SQL = """
SELECT  loai   AS kind,
        gia_tri AS value
FROM    v_tai_san_dam_bao
WHERE   mst = :tax_code
"""


OUTSTANDING_SQL = """
SELECT  du_no
FROM    v_du_no
WHERE   mst = :tax_code
"""

TRANSACTION_SUMMARY_SQL = """
SELECT  ky, ghi_no, ghi_co, so_du_binh_quan, so_luong_gd
FROM    v_t24_giao_dich_tong_hop
WHERE   mst = :tax_code AND ky BETWEEN :from_date AND :to_date
ORDER   BY ky
"""

CASHFLOW_PDLD_SQL = """
SELECT  COUNT(*) AS so_lan
FROM    v_giao_dich_pdld
WHERE   mst = :tax_code AND ngay_giao_dich BETWEEN :from_date AND :to_date
"""


@tool("get_t24_facilities", extras={"heading": "[T24 — HẠN MỨC ĐÃ HẠCH TOÁN]"})
def get_t24_facilities(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Active limits per product, the booking date, and the CCR on the BBC."""

    facilities = rows(executor, T24_FACILITIES_SQL, {"tax_code": tax_code})
    if not facilities:
        return {}
    return {
        "active_limit_by_product": {r["san_pham"]: r["hmtd_active"] for r in facilities},
        "active_limit": sum(r.get("hmtd_active") or 0 for r in facilities),
        "booking_date": min(r["ngay_hach_toan"] for r in facilities),
        "ccr": facilities[0].get("ccr"),
    }


@tool("get_collateral", extras={"heading": "[TÀI SẢN ĐẢM BẢO]"})
def get_collateral(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> list[dict]:
    """Collateral held against the facility: kind and value."""

    return rows(executor, COLLATERAL_SQL, {"tax_code": tax_code})


@tool("get_outstanding", extras={"heading": "[T24 — DƯ NỢ]"})
def get_outstanding(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Total outstanding obligation at TCB (BRD row 10). """

    row = one_row(executor, OUTSTANDING_SQL, {"tax_code": tax_code})
    return {"outstanding": row.get("du_no")} if row else {}


@tool("get_transaction_summary", extras={"heading": "[T24 — GIAO DỊCH TÀI KHOẢN THEO KỲ]"})
def get_transaction_summary(
    tax_code: Annotated[str, InjectedToolArg],
    from_date: Annotated[str, InjectedToolArg],
    to_date: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> list[dict]:
    """The customer's account activity per period, approval date to review date. """

    return rows(executor, TRANSACTION_SUMMARY_SQL,
                {"tax_code": tax_code, "from_date": from_date, "to_date": to_date})


@tool("get_cashflow_pdld", extras={"heading": "[GIAO DỊCH DÒNG TIỀN]"})
def get_cashflow_pdld(
    tax_code: Annotated[str, InjectedToolArg],
    from_date: Annotated[str, InjectedToolArg],
    to_date: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """How many LDs fell overdue (PDLD - Payment due LD) over the period under review. """

    row = one_row(executor, CASHFLOW_PDLD_SQL,
                  {"tax_code": tax_code, "from_date": from_date, "to_date": to_date})
    return {"pdld_count": row.get("so_lan")} if row else {}


