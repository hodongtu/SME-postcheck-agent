"""BL/WL - the black list and the warning list (BRD 1.2, 2.3.b, 2.4). """

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import rows


# An entry is in force on a date when it had been added by then and had not yet
# been removed. `ngay_ra` NULL means still listed.
BLWL_LIST_SQL = """
SELECT  loai_danh_sach AS list_kind,
        mst            AS tax_code,
        so_cccd        AS id_number,
        ten            AS name,
        ly_do          AS reason,
        ngay_vao       AS listed_on,
        ngay_ra        AS delisted_on
FROM    v_danh_sach_black_warning_list
WHERE   ngay_vao <= :as_of_date
  AND   (ngay_ra IS NULL OR ngay_ra > :as_of_date)
"""


@tool("get_blacklist_watchlist", extras={"heading": "[DANH SÁCH BLACK LIST / WARNING LIST]"})
def get_blacklist_watchlist(
    as_of_date: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Every black-list and warning-list entry in force on the given date. """

    return {"entries": rows(executor, BLWL_LIST_SQL, {"as_of_date": as_of_date})}
