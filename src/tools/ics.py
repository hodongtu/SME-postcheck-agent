"""CIC - the credit bureau. Debt groups and registered collateral (BRD 1.2, 2.4). """

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import rows


CIC_DEBT_GROUP_SQL = """
SELECT  doi_tuong, nhom_no
FROM    v_cic_nhom_no
WHERE   mst = :tax_code AND ngay_tra_cuu <= :as_of_date
ORDER   BY ngay_tra_cuu DESC
"""

CIC_SHAREHOLDER_DEBT_GROUP_SQL = """
SELECT  so_cccd AS id_number,
        nhom_no AS debt_group
FROM    v_cic_nhom_no_ca_nhan
WHERE   so_cccd IN ({placeholders}) AND ngay_tra_cuu <= :as_of_date
ORDER   BY ngay_tra_cuu DESC
"""

CIC_COLLATERAL_SQL = """
SELECT  tctd            AS lender,
        loai_tai_san    AS kind,
        mo_ta_tai_san   AS description,
        gia_tri         AS value,
        ngay_giai_chap  AS released_on
FROM    v_cic_tai_san_dam_bao
WHERE   mst = :tax_code
"""


@tool("get_cic_debt_groups", extras={"heading": "[CIC — NHÓM NỢ]"})
def get_cic_debt_groups(
    tax_code: Annotated[str, InjectedToolArg],
    as_of_date: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Debt group of the customer and the owner as CIC held it on a given date. """

    by_subject: dict[str, Any] = {}
    for row in rows(executor, CIC_DEBT_GROUP_SQL,
                    {"tax_code": tax_code, "as_of_date": as_of_date}):
        by_subject.setdefault(row["doi_tuong"], row["nhom_no"])
    if not by_subject:
        return {}
    return {"customer": by_subject.get("KH"), "owner": by_subject.get("CDN")}


@tool("get_cic_collateral", extras={"heading": "[CIC — TÀI SẢN ĐẢM BẢO ĐÃ ĐĂNG KÝ]"})
def get_cic_collateral(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> list[dict]:
    """Assets pledged at any lender, as registered with CIC. """

    return rows(executor, CIC_COLLATERAL_SQL, {"tax_code": tax_code})


@tool("get_cic_shareholder_debt_groups", extras={"heading": "[CIC — NHÓM NỢ CỔ ĐÔNG]"})
def get_cic_shareholder_debt_groups(
    shareholders: Annotated[list, InjectedToolArg],
    as_of_date: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Debt group of each shareholder, keyed by NAME so the report can say whose. """

    by_id = {
        str(person.get("id_number") or "").strip(): str(person.get("name") or "").strip()
        for person in shareholders or []
    }
    identifiable = [key for key in by_id if key]
    if not identifiable:
        return {}

    placeholders = ", ".join(f":id{index}" for index in range(len(identifiable)))
    params: dict[str, Any] = {f"id{index}": value
                              for index, value in enumerate(identifiable)}
    params["as_of_date"] = as_of_date

    latest: dict[str, Any] = {}
    for row in rows(executor, CIC_SHAREHOLDER_DEBT_GROUP_SQL.format(
            placeholders=placeholders), params):
        latest.setdefault(str(row.get("id_number") or "").strip(), row.get("debt_group"))

    return {name: latest.get(key) for key, name in by_id.items() if name}
