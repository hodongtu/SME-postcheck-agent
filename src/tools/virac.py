"""Virac - the only third-party data source in the system (BRD 2.4). """

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import rows


VIRAC_SQL = """
SELECT  nam, doanh_thu, lnst
FROM    v_virac_tai_chinh
WHERE   mst = :tax_code
"""


@tool("get_virac_financials", extras={"heading": "[VIRAC — TÀI CHÍNH DOANH NGHIỆP]"})
def get_virac_financials(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Revenue and net profit by year, as Virac holds them."""

    found = rows(executor, VIRAC_SQL, {"tax_code": tax_code})
    if not found:
        return {}
    return {
        "revenue_by_year": {str(r["nam"]): r["doanh_thu"] for r in found
                            if r.get("doanh_thu") is not None},
        "net_profit_by_year": {str(r["nam"]): r["lnst"] for r in found
                               if r.get("lnst") is not None},
    }
