"""Portfolio - a SECONDARY source, built by the portfolio team.

Unlike every other system this project queries, this one holds no original record: LOS is
where the approval was made, T24 is where the limit was booked, CIC is the bureau
itself. Portfolio is derived from those - assembled downstream by another team -
so two things follow that a core system would not impose:

  - it can LAG. A figure here may reflect an earlier state of T24, so a difference
    between the two is not automatically a finding about the customer.
  - it can be REBUILT. Column names and grain are the portfolio team's to change,
    which is why the rows are carried through verbatim instead of mapped onto
    named fields here.

That is also why nothing grades it yet: a criterion comparing derived data against
the system of record needs the tolerance for that lag to be stated first.

View and column names below are the surface to reconcile with the real system.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import rows


# Every facility the customer holds at the bank, not only the one under review.
# The columns are a placeholder shape: the fact carries the rows through as they
# arrive and the report prints a count, so nothing downstream depends on them.
PORTFOLIO_SQL = """
SELECT  san_pham, so_hop_dong, du_no, ngay_giai_ngan, ngay_dao_han, nhom_no
FROM    v_danh_muc_tin_dung
WHERE   mst = :tax_code
"""


@tool("get_portfolio", extras={"heading": "[PORTFOLIO — DANH MỤC TÍN DỤNG TẠI TCB]"})
def get_portfolio(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> list[dict]:
    """The customer's whole credit portfolio, as the portfolio team holds it.

    Collected and printed, not graded: declared in DISPLAY_ONLY_FACTS
    (src/facts.py). See the module docstring for why a derived source is not
    compared against T24 without a stated tolerance.
    """

    return rows(executor, PORTFOLIO_SQL, {"tax_code": tax_code})
