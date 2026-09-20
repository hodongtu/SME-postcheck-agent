"""CIC - the credit bureau. Debt groups and registered collateral (BRD 1.2, 2.4).

Post-check reads CIC from a query, not from a report in the dossier: the same
lookup is needed at two moments - the approval date and the review date - and a
file only ever carries one of them.

View and column names below are the surface to reconcile with the real system.
"""

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

# Shareholders are looked up by national ID, not by tax code: they are people,
# and the company's tax code says nothing about their own credit history.
CIC_SHAREHOLDER_DEBT_GROUP_SQL = """
SELECT  so_cccd AS id_number,
        nhom_no AS debt_group
FROM    v_cic_nhom_no_ca_nhan
WHERE   so_cccd IN ({placeholders}) AND ngay_tra_cuu <= :as_of_date
ORDER   BY ngay_tra_cuu DESC
"""

# Aliased in the SQL so every collateral fact in the system is read with the same
# English keys, whichever system it came from.
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
    """Debt group of the customer and the owner as CIC held it on a given date.

    INTEGRATION REQUIREMENT: the view must return ONE ROW PER SUBJECT (KH and
    CDN), including a subject whose debt is clean. If it only returns rows for
    subjects in trouble, then "no rows" means both "clean" and "the lookup never
    ran", and the system would read a failed lookup as group 1. Here no rows
    means UNKNOWN and the rules stop at insufficient data.

    Rows are ordered newest first, so the first row per subject at or before the
    date is the state as of that date.
    """

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
    """Assets pledged at any lender, as registered with CIC.

    `released_on` is the one that matters most: empty means the asset is still
    pledged, filled means it is not - a facility booked as secured against a
    released asset is a real finding (O07).
    """

    return rows(executor, CIC_COLLATERAL_SQL, {"tax_code": tax_code})


@tool("get_cic_shareholder_debt_groups", extras={"heading": "[CIC — NHÓM NỢ CỔ ĐÔNG]"})
def get_cic_shareholder_debt_groups(
    shareholders: Annotated[list, InjectedToolArg],
    as_of_date: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Debt group of each shareholder, keyed by NAME so the report can say whose.

    Looked up by national ID; a shareholder LOS recorded without one cannot be
    looked up at all and is returned as None, which keeps "no ID on file" apart
    from "clean". An empty result for a shareholder who does have an ID means the
    bureau returned no row, and that is None as well - never group 1.
    """

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
