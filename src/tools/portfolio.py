"""Portfolio - a SECONDARY source, built by the portfolio team. """

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import rows


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
    """The customer's whole credit portfolio, as the portfolio team holds it. """

    return rows(executor, PORTFOLIO_SQL, {"tax_code": tax_code})
