"""BEP - the approval system. What head office decided (BRD 1.1).

Same shape as SME_creditmemo's src/tools/t24.py: the SQL is a module constant,
every argument is an InjectedToolArg so a model can never fill one in, and the
pipeline calls the tool and writes the result into Facts.

View and column names below are the surface to reconcile with the real system.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import one_row, rows


BEP_APPROVAL_SQL = """
SELECT  ten_kh, mst, dia_chi,
        ten_cdn, cccd_cdn, nam_sinh_cdn,
        ma_gso, nganh_nghe, chuong_trinh,
        hmtd_phe_duyet, dt_sto,
        batch_hieu_luc_tu, batch_het_hieu_luc
FROM    v_bep_phe_duyet
WHERE   mst = :tax_code
"""

BEP_LIMIT_BY_PRODUCT_SQL = """
SELECT  san_pham, hmtd_phe_duyet
FROM    v_bep_han_muc_san_pham
WHERE   mst = :tax_code
"""


@tool("get_bep_approval", extras={"heading": "[BEP — HỒ SƠ PHÊ DUYỆT]"})
def get_bep_approval(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Customer details and the credit limit approved on BEP."""

    row = one_row(executor, BEP_APPROVAL_SQL, {"tax_code": tax_code})
    if not row:
        return {}
    row["hmtd_phe_duyet_theo_sp"] = {
        item["san_pham"]: item["hmtd_phe_duyet"]
        for item in rows(executor, BEP_LIMIT_BY_PRODUCT_SQL, {"tax_code": tax_code})
    }
    return row
