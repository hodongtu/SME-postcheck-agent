"""LOS - the approval system (BRD 1.1).

LOS holds four kinds of information about a file, and they are four queries here
rather than one wide row, because they have different grain and different
purpose:

  1. the file record   - the approval itself: limits, legal representative, chief
                         accountant, the batch's validity window
  2. top 5 shareholders - each a subject of the same list and bureau lookups as
                         the company and its owner
  3. site visit, online - the site visit as the RM keyed it in
  4. statements, online - the financial statements as the RM keyed them in

The last two matter more than they look. They are the RM's own account of the
same facts the dossier documents carry, entered by hand into a system - so they
are a second source to compare against, and a difference between what the RM
keyed and what the paperwork says is exactly the kind of finding this review
exists to surface. They are NOT a substitute for reading the documents.

Same shape as SME_creditmemo's src/tools/t24.py: the SQL is a module constant,
every argument is an InjectedToolArg so a model can never fill one in, and the
pipeline calls the tool and writes the result into Facts.

View and column names below are the surface to reconcile with the real system.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import one_row, rows


# ONE ROW PER PRODUCT, with the file-level fields repeated on each - the same
# shape as v_t24_han_muc, which is what the approved limits are compared against.
#
# `hmtd_phe_duyet` is the file's TOTAL and `hmtd_phe_duyet_san_pham` the product's
# share. The total is read, never summed from the parts: where a file carries an
# umbrella limit smaller than the sum of its sub-limits, deriving it would quietly
# raise the ceiling O02 measures against.
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

# Top five by stake. `ty_le` is the ownership percentage: the BRD singles out
# holders of 30% or more as subjects of a credit-bureau lookup, so the figure is
# carried through rather than dropped.
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
    """Customer details, the people on the file, and the credit limit approved.

    The rows differ only in their product, so the first carries every file-level
    field; the product column is folded into one mapping for O02 to compare
    against what T24 booked.
    """

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
    """The five largest shareholders: name, national ID, and stake.

    Each is a subject in their own right - the list and bureau lookups run over
    them as well as over the company and its legal representative.
    """

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
    """The financial statements as the RM keyed them into LOS, latest year first.

    Returns the most recent year only: the comparison downstream is against the
    reporting year of the statements in the dossier, and offering several years
    here would invite comparing two different periods.
    """

    found = rows(executor, LOS_FINANCIALS_ONLINE_SQL, {"tax_code": tax_code})
    return found[0] if found else {}
