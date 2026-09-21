"""LOS - the approval system (BRD 1.1). """

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import one_row, rows


LOS_APPROVAL_SQL = """
SELECT  ten_kh, mst, dia_chi,
        ten_cdn, cccd_cdn, nam_sinh_cdn,
        ten_ke_toan_truong,
        ma_gso, nganh_nghe, chan_dung, co_khao_sat_thuc_dia, chuong_trinh,
        hmtd_phe_duyet, san_pham, hmtd_phe_duyet_san_pham,
        dt_sto,
        batch_hieu_luc_tu, batch_het_hieu_luc
FROM    v_los_phe_duyet
WHERE   mst = :tax_code
"""

LOS_SHAREHOLDERS_SQL = """
SELECT  ten     AS name,
        so_cccd AS id_number,
        ty_le   AS stake_pct
FROM    v_los_co_dong
WHERE   mst = :tax_code
ORDER   BY ty_le DESC
LIMIT   5
"""

LOS_SITEVISIT_ONLINE_SQL = """
SELECT  nganh_nghe, dia_chi, ngay_khao_sat
FROM    v_los_khao_sat_online
WHERE   mst = :tax_code
"""

LOS_FINANCIALS_ONLINE_SQL = """
SELECT  nam, loai_bao_cao, doanh_thu, lnst
FROM    v_los_bctc_online
WHERE   mst = :tax_code
ORDER   BY nam DESC
"""


@tool("get_los_approval", extras={"heading": "[LOS — HỒ SƠ PHÊ DUYỆT]"})
def get_los_approval(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Customer details, the people on the file, and the credit limit approved. """

    found = rows(executor, LOS_APPROVAL_SQL, {"tax_code": tax_code})
    if not found:
        return {}

    record = dict(found[0])
    record["hmtd_phe_duyet_theo_sp"] = {
        row["san_pham"]: row["hmtd_phe_duyet_san_pham"]
        for row in found if row.get("san_pham")
    }
    # Per-product columns off the first row would read as the whole file's limit.
    record.pop("san_pham", None)
    record.pop("hmtd_phe_duyet_san_pham", None)
    return record


@tool("get_los_shareholders", extras={"heading": "[LOS — TOP 5 CỔ ĐÔNG GÓP VỐN]"})
def get_los_shareholders(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> list[dict]:
    """The five largest shareholders: name, national ID, and stake. """

    return rows(executor, LOS_SHAREHOLDERS_SQL, {"tax_code": tax_code})


@tool("get_los_sitevisit_online", extras={"heading": "[LOS — KHẢO SÁT THỰC ĐỊA (RM NHẬP)]"})
def get_los_sitevisit_online(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """The site visit as the RM keyed it into LOS, to compare with the report filed."""

    return one_row(executor, LOS_SITEVISIT_ONLINE_SQL, {"tax_code": tax_code})


@tool("get_los_financials_online", extras={"heading": "[LOS — BCTC (RM NHẬP)]"})
def get_los_financials_online(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """The financial statements as the RM keyed them into LOS, latest year first. """

    found = rows(executor, LOS_FINANCIALS_ONLINE_SQL, {"tax_code": tax_code})
    return found[0] if found else {}
