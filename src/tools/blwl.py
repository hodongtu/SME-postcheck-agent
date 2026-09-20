"""BL/WL - the black list and the warning list (BRD 1.2, 2.3.b, 2.4).

A list of its own, not a view onto another system: it is maintained separately
from BCDE and from the credit bureau, and the AMC recovery list beside it in
src/tools/amc.py is a third, independent one.

This is a LIST query, not a per-customer flag: the tool returns the entries in
force on a given date, and matching the customer and the business owner against
them happens in the pipeline. That is the shape the business described - if the
company or its owner appears in the list, it is a hit - and it has a property the
per-customer form did not: the matched entry can be named in the report, so a
finding says which list and on what grounds.

The BRD names three moments for this lookup: section 1.2 at collection, 2.3.b at
appraisal, 2.4 at review time. One query with an as-of date answers all three; it
is called twice, once per moment.

View and column names below are the surface to reconcile with the real system.
"""

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
    """Every black-list and warning-list entry in force on the given date.

    No customer filter: the caller matches against the list. Deliberately so -
    membership is decided on a tax code OR a national ID OR a name, and pushing
    that OR into SQL would turn this back into a per-customer flag.

    An EMPTY list means NOBODY IS LISTED, and the subjects come back clean. That
    is the business's decision, and it has a cost worth knowing: a lookup that
    breaks by returning no rows - rather than by raising - is indistinguishable
    from a clean answer. A query that raises is still reported as missing data.

    The rows are wrapped in a dict so an empty list survives the pipeline's
    "no data" check, which treats a falsy tool result as a failed query.

    If the real list is large enough that fetching it per review is wasteful, the
    fix is a date-and-subject-scoped view, not a WHERE on the customer here.
    """

    return {"entries": rows(executor, BLWL_LIST_SQL, {"as_of_date": as_of_date})}
