"""The rule engine: types, the missing-data guard, and the runner.

The guard is the point of this module. A rule's `check` never sees a MISSING
fact, because the runner refuses to call it when one of the facts it declared
is absent - and `Verdict` cannot express insufficient data, so a rule cannot
reach that state on its own either. Both halves matter: the first stops a rule
from reading an empty cell, the second stops it from claiming it checked
something it did not.

This is load-bearing, and measured. Remove the gate and call `check` directly
on a full dossier with exactly one fact deleted: 14 of 84 combinations return
PASS instead of failing, among them the one announcing that neither customer
nor owner is on the black or warning list, when that lookup returned nothing.

Identifiers and comments are English; the strings a reviewer reads are
Vietnamese.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Literal

from src.facts import FACT_KEYS, Facts


Status = Literal["PASS", "FAIL", "INSUFFICIENT_DATA"]
Severity = Literal["high", "medium", "low"]

STATUS_LABELS: dict[str, str] = {
    "PASS": "Đạt",
    "FAIL": "Không đạt",
    "INSUFFICIENT_DATA": "Thiếu dữ liệu",
}
SEVERITY_LABELS: dict[str, str] = {
    "high": "Cao",
    "medium": "Trung bình",
    "low": "Thấp",
}
NOT_CHECKED_PREFIX = "Chưa kiểm được."


@dataclass(frozen=True)
class Verdict:
    """What a rule concluded. Deliberately cannot say insufficient data.

    There is no evidence field: `observed` already names the documents inline,
    beside the values that differ, which is both shorter and more use to a
    reader than a bare list of file names.
    """

    status: Literal["PASS", "FAIL"]
    observed: str                      # Vietnamese: printed in the report

    def __post_init__(self) -> None:
        if self.status not in ("PASS", "FAIL"):
            raise ValueError(
                f"Verdict.status = {self.status!r}. A rule may only conclude "
                f"PASS or FAIL; INSUFFICIENT_DATA is run_rules()'s decision."
            )
        if not str(self.observed).strip():
            raise ValueError("Verdict.observed is empty - it must state what was seen.")


def passed(observed: str) -> Verdict:
    return Verdict("PASS", observed)


def failed(observed: str) -> Verdict:
    return Verdict("FAIL", observed)


@dataclass(frozen=True)
class Rule:
    """One line of the BRD, expressed as something a machine can decide.

    A rule does NOT record where it is printed. src/templates/post-check-template.md
    owns that, with its `<!-- rules: ... -->` markers, so there is one place to
    look and one place to edit.
    """

    id: str                     # "O01"
    title: str                  # Vietnamese, verbatim from the BRD
    expected: str               # Vietnamese: the passing condition, for the reader
    severity: Severity
    needs: tuple[str, ...]      # paths declared in FACT_KEYS
    check: Callable[[Facts, dict], Verdict]


@dataclass(frozen=True)
class Finding:
    """One row of the output report."""

    rule_id: str
    title: str
    expected: str
    severity: Severity
    status: Status
    observed: str
    missing: tuple[str, ...] = field(default=())

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS[self.severity]


def run_rules(rules: tuple[Rule, ...], facts: Facts, settings: dict) -> list[Finding]:
    """Decide every rule. The missing-data gate lives here, not in the rules."""

    findings: list[Finding] = []
    for rule in rules:
        missing = facts.missing(rule.needs)
        if missing:
            findings.append(
                Finding(
                    rule_id=rule.id,
                    title=rule.title,
                    expected=rule.expected,
                    severity=rule.severity,
                    status="INSUFFICIENT_DATA",
                    observed=NOT_CHECKED_PREFIX
                    + " "
                    + "; ".join(facts.reason(path) for path in missing),
                    missing=tuple(missing),
                )
            )
            continue

        verdict = rule.check(facts, settings)
        findings.append(
            Finding(
                rule_id=rule.id,
                title=rule.title,
                expected=rule.expected,
                severity=rule.severity,
                status=verdict.status,
                observed=verdict.observed,
            )
        )
    return findings


def summarise(findings: list[Finding]) -> dict[str, int]:
    """Pass / fail / insufficient, counted separately and never merged."""

    return {
        "PASS": sum(1 for f in findings if f.status == "PASS"),
        "FAIL": sum(1 for f in findings if f.status == "FAIL"),
        "INSUFFICIENT_DATA": sum(1 for f in findings if f.status == "INSUFFICIENT_DATA"),
        "TOTAL": len(findings),
    }


# ---------------------------------------------------------------------------
# Helpers shared by the rule modules
# ---------------------------------------------------------------------------

def validate_needs(rules: tuple[Rule, ...]) -> None:
    """Every declared need must be a real fact. Called at import time."""

    problems: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if rule.id in seen:
            problems.append(f"{rule.id}: duplicate rule id")
        seen.add(rule.id)
        if not rule.needs:
            problems.append(f"{rule.id}: empty needs - every rule must read a fact")
        for path in rule.needs:
            if path not in FACT_KEYS:
                problems.append(f"{rule.id}: needs '{path}', which is not in FACT_KEYS")
    if problems:
        raise ValueError("Bad rule declarations:\n  " + "\n  ".join(problems))


def variance_pct(left: float, right: float) -> float | None:
    """Difference between two figures over the larger one. None when both are 0."""

    base = max(abs(left), abs(right))
    if base == 0:
        return None
    return abs(left - right) / base * 100.0


def as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
