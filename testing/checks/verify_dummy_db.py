"""Every query runs, and every column it returns lands on the fact that needs it.

The other eighteen checks never touch a query. They grade rules from JSON
fixtures, which is what makes them fast and free - and it means the whole
collection half of the system, nine tools and their SQL, is unverified: a typo in
a column name, a tool wired to the wrong fact, a view nobody selects from would
all read in a report as "not collected" for a customer.

So this one runs the real thing against samples/dummy_db: the same
`fetch_reference_data`, the same tools, the same SQL, an executor over a SQLite
file built to the shape the SQL expects. Still no LLM and still no network.

Four things must hold, and the last two are what catch a rewiring:

  1. the dataset and the SQL cover each other - every table a tool selects from
     exists, and no table sits in the dataset that nothing selects from
  2. no query fails - the table and column names in src/tools/ resolve
  3. every fact whose source is a system has a VALUE, not a reason
  4. the rules that read those facts reach a pass-or-fail verdict, and the two
     customers get different answers - identical verdicts would mean the data
     never reached the rules
  5. a tax code the database does not hold is reported AS THAT, not as a dossier
     with missing documents - the two are indistinguishable in the verdict
     counts, and the wrong one sends a reviewer back to the business unit for
     papers that are already in the folder
  6. an empty BL/WL or AMC means nobody is listed - the business chose this over
     reading it as a failed lookup, and the choice is asserted so it cannot drift
  7. the four date filters actually filter. BL/WL, AMC, PDLD and the transaction
     rollup each scope their
     rows to a moment, and a query that lost its date clause would still return
     plausible data - so the dataset carries a row on the wrong side of each
     boundary, and this asserts it stays out

The dataset carries two customers so the failing half is reachable too. If it
ever stops catching things, delete a table from make_dummy_db.SCHEMA and confirm
this check goes red before trusting it again.
"""

from _harness import ROOT, report
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


OK_CUSTOMER = "0201123795"
BAD_CUSTOMER = "0209999999"

# The dates the dummy dataset is built around: an approval window in 2026 and a
# review after it. make_dummy_db explains why the booking date sits where it does.
APPROVAL_DATE = "2026-04-01"
POSTCHECK_DATE = "2026-09-15"


def main() -> int:
    sys.path.insert(0, str(ROOT / "samples" / "dummy_db"))
    import make_dummy_db

    from src.config import Config
    from src.facts import DISPLAY_ONLY_FACTS, Facts, db_facts as system_facts
    from src.pipeline import fetch_reference_data, run_postcheck
    from src.settings import get_settings
    from src.tools._executor import sqlite_executor

    problems: list[str] = []

    db_path = make_dummy_db.build(ROOT / "samples" / "dummy_db" / "postcheck_dummy.sqlite")
    executor = sqlite_executor(str(db_path))
    settings = get_settings()

    db_facts = system_facts()

    # --- 1: the dataset and the SQL cover each other ------------------------
    # Read off the SQL text rather than the tool objects: a table this dataset
    # lacks fails the query below anyway, but a table the dataset still carries
    # after its tool was deleted would go unnoticed, and stale fixtures are how a
    # check starts passing for the wrong reason.
    statements: dict[str, str] = {}
    for module in sorted((ROOT / "src" / "tools").glob("*.py")):
        for match in re.finditer(
            r'^([A-Z_0-9]+_SQL)\s*=\s*"""(.*?)"""',
            module.read_text(encoding="utf-8"), re.S | re.M,
        ):
            statements[f"{module.name}:{match.group(1)}"] = match.group(2)

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0] for row in
            connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    selected: set[str] = set()
    for name, text in sorted(statements.items()):
        used = set(re.findall(r"FROM\s+(\w+)", text))
        selected |= used
        for table in sorted(used - tables):
            problems.append(f"{name} selects from '{table}', which the dataset has no")
    for table in sorted(tables - selected):
        problems.append(
            f"the dataset carries '{table}' that no SQL selects from - either a tool "
            f"was deleted and this table outlived it, or a query is missing"
        )
    if not statements:
        problems.append("no *_SQL constants found under src/tools/ - the scan is broken")

    # --- 2 and 3: the queries run, and they fill what they owe --------------
    facts = Facts()
    fetch_reference_data(facts, OK_CUSTOMER, Config(query_executor=executor),
                         APPROVAL_DATE, POSTCHECK_DATE, settings)
    reasons = facts.to_dict()["reasons"]
    for path in db_facts:
        if path in reasons:
            problems.append(f"{path}: query left it missing - {reasons[path]}")

    # --- 4: the rules downstream actually grade, both ways round ------------
    verdicts: dict[str, dict[str, str]] = {}
    for tax_code, label in ((OK_CUSTOMER, "clean"), (BAD_CUSTOMER, "failing")):
        result = run_postcheck(
            case_dir=ROOT / "samples" / "case_demo",
            config=Config(query_executor=executor),   # executor wired, no LLM
            tax_code=tax_code,
            approval_date=APPROVAL_DATE,
            postcheck_date=POSTCHECK_DATE,
        )
        verdicts[label] = {f.rule_id: f.status for f in result.findings}
        if not result.report_markdown.strip():
            problems.append(f"{label}: run_postcheck returned an empty report")

    # A rule reading only system facts has no excuse for insufficient data here.
    from src.rules.registry import RULES

    system_only = {
        rule.id for rule in RULES
        if set(rule.needs) <= set(db_facts) | {"case.postcheck_date"}
    }
    for label, graded_rules in verdicts.items():
        for rule_id in sorted(system_only):
            if graded_rules.get(rule_id) == "INSUFFICIENT_DATA":
                problems.append(
                    f"{label}: {rule_id} reads only system facts, yet it stopped at "
                    f"insufficient data with the database wired"
                )

    # Compared in aggregate, not rule by rule: several rules legitimately pass for
    # both customers (both programs are valid, both industries are correctly
    # classified). What cannot happen is the whole suite answering the same for two
    # customers whose data differs in every table - that is what a broken wiring
    # between a query result and a fact looks like from the outside.
    differing = [rule_id for rule_id in system_only
                 if verdicts["clean"].get(rule_id) != verdicts["failing"].get(rule_id)]
    if len(differing) < 2:
        problems.append(
            f"only {len(differing)} of {len(system_only)} system-fact rules answer "
            f"differently for the two customers - the query results are not reaching "
            f"the rules"
        )

    # --- 5: a customer the database does not hold says so ---------------------
    unknown = run_postcheck(
        case_dir=ROOT / "samples" / "case_demo",
        config=Config(query_executor=executor),
        tax_code="0000000000",                   # in no table of the dataset
        approval_date=APPROVAL_DATE,
        postcheck_date=POSTCHECK_DATE,
    )
    known_report = run_postcheck(
        case_dir=ROOT / "samples" / "case_demo",
        config=Config(query_executor=executor),
        tax_code=OK_CUSTOMER,
        approval_date=APPROVAL_DATE,
        postcheck_date=POSTCHECK_DATE,
    ).report_markdown
    banner = "Không tìm thấy hồ sơ phê duyệt trên LOS"
    if banner not in unknown.report_markdown:
        problems.append(f"the unknown-customer report is missing the banner {banner!r}")
    if banner in known_report:
        problems.append(
            f"the banner {banner!r} also appears for a customer the database DOES "
            f"hold - it would cry wolf on every run"
        )

    # --- 6: an empty list means nobody is listed, not a broken lookup ---------
    # The business chose this over the safer reading, so it is asserted rather
    # than left to whichever branch of _query happens to run: with both lists
    # emptied, every BL/WL and AMC fact must carry a value of False, not a reason.
    empty_db = Path(tempfile.mkdtemp()) / "empty_lists.sqlite"
    shutil.copy(db_path, empty_db)
    with sqlite3.connect(empty_db) as connection:
        connection.execute("DELETE FROM v_danh_sach_black_warning_list")
        connection.execute("DELETE FROM v_danh_sach_amc")

    cleared = Facts()
    fetch_reference_data(cleared, BAD_CUSTOMER,
                         Config(query_executor=sqlite_executor(str(empty_db))),
                         APPROVAL_DATE, POSTCHECK_DATE, settings)
    cleared_reasons = cleared.to_dict()["reasons"]
    for path in db_facts:
        if not path.startswith(("blwl.", "amc.")):
            continue
        if path in cleared_reasons:
            problems.append(
                f"with both lists empty, {path} came back missing - an empty list must "
                f"read as nobody listed, not as a lookup that did not run"
            )
            continue
        value = cleared.get(path)
        hit = any(value.values()) if isinstance(value, dict) else bool(value)
        if hit:
            problems.append(
                f"with both lists empty, {path} still reports a hit ({value!r})"
            )

    # --- 7: the date clauses are load-bearing -------------------------------
    from src.tools import amc, blwl, t24

    # Both lists carry an entry closed before the approval date, so each is in
    # force at the earlier date and gone at the later one. Both directions, or the
    # assertion proves nothing.
    for label, fetch in (("BL/WL", blwl.get_blacklist_watchlist),
                         ("AMC", amc.get_amc_recovery_list)):
        before = {e.get("name") for e in fetch.invoke(
            {"as_of_date": "2026-01-15", "executor": executor})["entries"]}
        after = {e.get("name") for e in fetch.invoke(
            {"as_of_date": APPROVAL_DATE, "executor": executor})["entries"]}
        if not before - after:
            problems.append(
                f"the {label} as-of filter drops nothing between 2026-01-15 and "
                f"{APPROVAL_DATE} - either the dataset lost its closed entry or the "
                f"date clause in its SQL is not filtering"
            )

    # PDLD and the transaction rollup: each has a row before the approval date
    # that must not be counted.
    windowed = (
        ("PDLD", BAD_CUSTOMER,
         lambda **kw: t24.get_cashflow_pdld.invoke(kw)["pdld_count"]),
        ("transaction rollup", OK_CUSTOMER,
         lambda **kw: len(t24.get_transaction_summary.invoke(kw))),
    )
    for label, tax_code, count in windowed:
        inside = count(tax_code=tax_code, from_date=APPROVAL_DATE,
                       to_date=POSTCHECK_DATE, executor=executor)
        ever = count(tax_code=tax_code, from_date="0001-01-01",
                     to_date="9999-12-31", executor=executor)
        if inside >= ever:
            problems.append(
                f"{label} counts {inside} inside the review window and {ever} over all "
                f"time - nothing sits outside the window, so its date clause is untested"
            )

    graded = sum(1 for status in verdicts["clean"].values() if status != "INSUFFICIENT_DATA")
    failed_on_bad = sum(1 for status in verdicts["failing"].values() if status == "FAIL")

    # Collected for the report and never graded: the value must still arrive.
    for path in DISPLAY_ONLY_FACTS:
        if path in reasons:
            problems.append(f"{path} is display-only, but the query did not fill it")

    return report(
        problems,
        f"{len(statements)} SQL statements over {len(tables)} tables, each covering "
        f"the other; {len(db_facts)} system facts all filled; case_demo grades "
        f"{graded}/{len(verdicts['clean'])} rules with no LLM, and the "
        f"out-of-tolerance customer trips {failed_on_bad} of them "
        f"({len(differing)} system-fact rules answer differently); all three date "
        f"filters exclude a row on the wrong side of their boundary",
    )


if __name__ == "__main__":
    sys.exit(main())
