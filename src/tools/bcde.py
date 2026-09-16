"""BCDE - where the appraisal officer's lookups were filed (BRD 2.3.b).

The BRD contradicts itself on where CIC and BL/WL come from: section 1.2 says
Database, section 2.3.b says the CIC report was uploaded onto BCDE, and
section 2.4 says a fresh ICS lookup. BCDE resolves it: the officer looked the customer up
and filed the result here at appraisal time, so at post-check that state is a
SQL query. The fresh lookup at review time arrives as a file in the dossier and
is read by the cic_s10a extraction pass instead.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolArg, tool

from src.tools._executor import rows


BCDE_CIC_SQL = """
SELECT  doi_tuong, nhom_no
FROM    v_bcde_cic_nhom_no
WHERE   mst = :tax_code
"""

BCDE_BLWL_SQL = """
SELECT  doi_tuong, danh_sach
FROM    v_bcde_black_warning_list
WHERE   mst = :tax_code
"""


@tool("get_bcde_cic", extras={"heading": "[BCDE — NHÓM NỢ TẠI THỜI ĐIỂM PHÊ DUYỆT]"})
def get_bcde_cic(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Debt group of the customer and the owner as filed at appraisal time."""

    by_subject = {
        row["doi_tuong"]: row["nhom_no"]
        for row in rows(executor, BCDE_CIC_SQL, {"tax_code": tax_code})
    }
    if not by_subject:
        return {}
    return {"customer": by_subject.get("KH"), "owner": by_subject.get("CDN")}


@tool("get_bcde_blwl", extras={"heading": "[BCDE — BLACK LIST / WARNING LIST]"})
def get_bcde_blwl(
    tax_code: Annotated[str, InjectedToolArg],
    executor: Annotated[Any, InjectedToolArg],
) -> dict:
    """Whether the customer and the owner were listed at appraisal time.

    INTEGRATION REQUIREMENT: the view must return ONE ROW PER SUBJECT (customer
    and owner) with a `danh_sach` flag, including subjects that are clean. If it
    only returns rows for people who are listed, then "no rows" means both
    "clean" and "the lookup never ran", and the system would read a failed
    lookup as a clean customer. Here no rows means UNKNOWN, and the rules stop
    at insufficient data.
    """

    found = rows(executor, BCDE_BLWL_SQL, {"tax_code": tax_code})
    if not found:
        return {}
    listed = {row["doi_tuong"] for row in found if row.get("danh_sach")}
    return {"customer": "KH" in listed, "owner": "CDN" in listed}
