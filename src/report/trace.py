"""Per-criterion trace: which facts a rule read, and what value each one held.

result.json already carries every fact and every conclusion, but not the join
between them: Rule.needs lives in the registry, so tracing a verdict by hand means
cross-referencing 40 rules against 78 facts. This writes that join out.
"""

from typing import Any

from src.facts import FACT_KEYS, Facts
from src.rules.engine import Finding
from src.rules.registry import RULES

STATUS_LABEL = {
    "PASS": "Đạt",
    "FAIL": "Không đạt",
    "INSUFFICIENT_DATA": "Thiếu dữ liệu",
}


def _input_row(facts: Facts, path: str) -> dict[str, Any]:
    spec = FACT_KEYS.get(path)
    row: dict[str, Any] = {
        "path": path,
        "description": spec.description if spec else "",
        "category": spec.category if spec else "",
        "delivery": spec.delivery if spec else "",
        "present": facts.has(path),
    }
    if facts.has(path):
        row["value"] = facts.get(path)
        # An empty list can be an answer - "nobody is on the watchlist" - and the
        # trace has to say which, or an empty value reads as a failed lookup.
        note = facts.empty_note(path)
        if note:
            row["empty_note"] = note
    else:
        row["value"] = None
        row["missing_reason"] = facts.missing_reason(path)
    return row


def criteria_trace(findings: list[Finding], facts: Facts) -> dict[str, Any]:
    """One entry per rule: its verdict, and every fact it was given. """

    needs = {rule.id: rule.needs for rule in RULES}
    trace: dict[str, Any] = {}
    for finding in findings:
        trace[finding.rule_id] = {
            "title": finding.title,
            "status": finding.status,
            "status_label": STATUS_LABEL.get(finding.status, finding.status),
            "expected": finding.expected,
            "observed": finding.observed,
            "inputs": [_input_row(facts, path)
                       for path in needs.get(finding.rule_id, ())],
            "missing": list(finding.missing),
        }
    return trace
