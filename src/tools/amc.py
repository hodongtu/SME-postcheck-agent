"""AMC - the debt-recovery list (no BRD row; requested by the business).

A third independent list beside BL/WL: being on it means the subject is already
in a recovery workflow. Same shape and same as-of semantics as
src/tools/blwl.py, and matched by the same code in the pipeline, so the two stay
comparable - but a separate list, separate table, separate fact.

View and column names below are the surface to reconcile with the real system.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import rows


# In force on a date when it had been opened by then and not yet closed.
AMC_LIST_SQL = """
SELECT  mst      AS tax_code,
        so_cccd  AS id_number,
        ten      AS name,
        ly_do    AS reason,
        ngay_vao AS listed_on,
        ngay_ra  AS delisted_on
FROM    v_danh_sach_amc
WHERE   ngay_vao <= :as_of_date
  AND   (ngay_ra IS NULL OR ngay_ra > :as_of_date)
"""


@tool("get_amc_recovery_list", extras={"heading": "[AMC — DANH SÁCH THU HỒI NỢ]"})
def get_amc_recovery_list(
    as_of_date: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Every subject in a recovery workflow on the given date.

    No customer filter, and an empty list means nobody is in recovery - both for
    the reasons set out in src/tools/blwl.py, including the cost of reading an
    empty result as clean.
    """

    return {"entries": rows(executor, AMC_LIST_SQL, {"as_of_date": as_of_date})}
