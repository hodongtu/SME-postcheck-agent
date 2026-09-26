"""The trace must explain every verdict, or it is not a trace.

Three claims, each one a way the export could be quietly useless:

  - it shows EXACTLY the facts the rule declared - no fewer (a hidden input) and
    no more (an input the rule never read, which would send the reader hunting for
    a comparison that does not happen);
  - every insufficient-data verdict names at least one absent fact AND says why
    that fact is absent;
  - every graded verdict shows every input present, which is what the missing-data
    gate promises and what makes the verdict reproducible by hand.
"""

from _harness import ROOT, report
import json
import sys

CASES = (("0201123795", "hồ sơ sạch"), ("0209999999", "hồ sơ ngoài ngưỡng"))


def main() -> int:
    from src.config import Config
    from src.pipeline import run_postcheck
    from src.report.trace import criteria_trace
    from src.rules.registry import RULES
    from src.tools._executor import sqlite_executor

    database = ROOT / "samples" / "dummy_db" / "postcheck_dummy.sqlite"
    if not database.exists():
        return report(["samples/dummy_db/postcheck_dummy.sqlite is missing; "
                       "run make_dummy_db.py"], "")

    needs = {rule.id: list(rule.needs) for rule in RULES}
    problems: list[str] = []
    traced = 0

    for tax_code, label in CASES:
        result = run_postcheck(
            case_dir=ROOT / "samples" / "case_demo",
            config=Config(query_executor=sqlite_executor(str(database))),
            tax_code=tax_code,
            approval_date="2026-04-01",
            postcheck_date="2026-09-15",
        )
        trace = criteria_trace(result.findings, result.facts)

        absent = set(needs) - set(trace)
        if absent:
            problems.append(f"{label}: no trace for {sorted(absent)}")

        try:
            json.dumps(trace, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            problems.append(f"{label}: the trace does not serialise to JSON - {exc}")

        for rule_id, entry in trace.items():
            traced += 1
            shown = [row["path"] for row in entry["inputs"]]
            if shown != needs.get(rule_id):
                problems.append(
                    f"{label}/{rule_id}: shows {shown} but the rule declares "
                    f"{needs.get(rule_id)}"
                )
            missing_rows = [row for row in entry["inputs"] if not row["present"]]
            if entry["status"] == "INSUFFICIENT_DATA":
                if not missing_rows:
                    problems.append(
                        f"{label}/{rule_id}: reported insufficient data but the "
                        f"trace shows every input present"
                    )
                elif not any(row.get("missing_reason") for row in missing_rows):
                    problems.append(
                        f"{label}/{rule_id}: names absent facts without saying why "
                        f"any of them is absent"
                    )
            elif missing_rows:
                problems.append(
                    f"{label}/{rule_id}: graded {entry['status']} although the trace "
                    f"shows {[row['path'] for row in missing_rows]} absent"
                )
            for row in entry["inputs"]:
                if not row["description"]:
                    problems.append(
                        f"{label}/{rule_id}: {row['path']} is traced with no "
                        f"description, so the reader gets a path and nothing else"
                    )

    return report(
        problems,
        f"{traced} (rule x dossier) traced: inputs match what each rule declares, "
        f"every insufficient-data verdict names an absent fact and its reason, and "
        f"every graded verdict shows all its inputs present",
    )


if __name__ == "__main__":
    sys.exit(main())
