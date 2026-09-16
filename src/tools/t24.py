"""T24 - the core banking system.

Everything the bank itself recorded: the limits it booked, the collateral it
holds, the customer's outstanding obligations, and their account activity.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import one_row, rows


T24_FACILITIES_SQL = """
SELECT  san_pham, hmtd_active, ngay_hach_toan, ccr
FROM    v_t24_han_muc
WHERE   mst = :tax_code
ORDER   BY ngay_hach_toan
"""

# Aliased in the SQL: the database column names stay where they belong, and
# every collateral fact in the system is then read with the same English keys.
COLLATERAL_SQL = """
SELECT  loai   AS kind,
        gia_tri AS value
FROM    v_tai_san_dam_bao
WHERE   mst = :tax_code
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
        # Earliest booking date: the reference point for the approval validity
        # check (O01) and for which financial year the statements must cover (P07).
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


@tool("get_cashflow_pdld", extras={"heading": "[GIAO DỊCH DÒNG TIỀN]"})
def get_cashflow_pdld(
    tax_code: Annotated[str, InjectedToolArg],
    from_date: Annotated[str, InjectedToolArg],
    to_date: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """How many PDLD transactions occurred over the period under review."""

    row = one_row(executor, CASHFLOW_PDLD_SQL,
                  {"tax_code": tax_code, "from_date": from_date, "to_date": to_date})
    return {"pdld_count": row.get("so_lan")} if row else {}


