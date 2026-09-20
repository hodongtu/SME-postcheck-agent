"""Load and validate config/programs.yaml.

Every threshold a rule reads comes from here. The loader is strict on purpose:
a checklist naming a document type that does not exist would otherwise become a
permanently-unsatisfiable requirement that nobody notices, and a missing
criterion would surface as a customer-facing failed criterion instead of a
configuration error.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.agents.documents.document_matrix import load_matrix
from src.utils.paths import PROJECT_ROOT


SETTINGS_PATH = PROJECT_ROOT / "config" / "programs.yaml"

REQUIRED_DEFAULTS = (
    "variance_threshold_pct",
    "financials_cutoff_mmdd",
    "unsecured_ccr_pct",
    "secured_collateral_types",
    "allowed_extensions",
    "balance_tolerance_vnd",
    "debt_group_warning_threshold",
    "max_pdld_count",
    "address_abbreviations",
)
VALID_REQUIREMENTS = frozenset({"mandatory", "recommended", "optional"})
# A checklist item may be required only under a condition. The only one so far
# is "site_visit": required when LOS says this file needs a field visit.
VALID_CONDITIONS = frozenset({"site_visit"})

# Every program must declare these, so that a configuration gap fails on load
# rather than surfacing in the report as a failed criterion for the customer.
REQUIRED_CRITERIA = ("max_cic_group", "BO_max_cic_group")


class SettingsError(RuntimeError):
    """config/programs.yaml is malformed."""


def _fail(message: str) -> None:
    raise SettingsError(f"config/programs.yaml: {message}")


def load_settings(path: Path | str | None = None) -> dict[str, Any]:
    """Read the settings file into the flat dict every rule receives."""

    target = Path(path) if path else SETTINGS_PATH
    if not target.exists():
        _fail(f"file not found at {target}")

    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    for key in REQUIRED_DEFAULTS:
        if key not in defaults:
            _fail(f"missing defaults.{key}")

    known_types = set(load_matrix().types)
    programs: dict[str, Any] = {}
    for entry in raw.get("programs") or []:
        program_id = entry.get("id")
        if not program_id:
            _fail("a program entry has no id")
        if program_id in programs:
            _fail(f"program '{program_id}' is declared twice")

        checklist = entry.get("checklist") or []
        if not checklist:
            _fail(f"program '{program_id}' has an empty checklist")
        for item in checklist:
            type_id = item.get("type_id")
            if type_id not in known_types:
                _fail(
                    f"program '{program_id}' references type_id '{type_id}', which is "
                    f"not in document_matrix.yaml"
                )
            if item.get("when") is not None and item["when"] not in VALID_CONDITIONS:
                _fail(
                    f"program '{program_id}', type '{type_id}': when "
                    f"'{item['when']}' must be one of {sorted(VALID_CONDITIONS)}"
                )
            if item.get("requirement") not in VALID_REQUIREMENTS:
                _fail(
                    f"program '{program_id}', type '{type_id}': requirement "
                    f"'{item.get('requirement')}' must be one of "
                    f"{sorted(VALID_REQUIREMENTS)}"
                )
        if not any(i.get("requirement") == "mandatory" for i in checklist):
            _fail(f"program '{program_id}' has no mandatory item")

        criteria = entry.get("criteria") or {}
        for key in REQUIRED_CRITERIA:
            if key not in criteria:
                _fail(f"program '{program_id}' is missing criteria.{key}")

        programs[program_id] = {
            "label": entry.get("label", program_id),
            "checklist": checklist,
            "criteria": criteria,
        }

    if not programs:
        _fail("no program is declared")

    settings = dict(defaults)
    settings["programs"] = programs
    # A blank list entry is an editing artefact, not a code; drop it rather than
    # let None reach the comparison as an industry nobody has. An empty list is a
    # legitimate state for both keys - it says "nothing classified yet", which is
    # different from a missing key, and that is why neither is required above.
    for key in ("focus_GSO", "restricted_GSO"):
        settings[key] = [
            str(code).strip() for code in (raw.get(key) or []) if str(code or "").strip()
        ]
    settings["debt_group_by_label"] = raw.get("debt_group_by_label") or {}
    settings["financial_report_types"] = raw.get("financial_report_types") or {}

    # A persona whose threshold exceeds the markers it declares can never be
    # satisfied, and V10 would fail every customer of that persona while the
    # report looked entirely normal. Caught on load, not on the run.
    personas = raw.get("persona_evidence") or {}
    for name, entry in personas.items():
        expected = (entry or {}).get("expected") or []
        minimum = (entry or {}).get("min_markers")
        if not expected:
            _fail(f"persona_evidence['{name}'] declares no expected markers")
        if not isinstance(minimum, int) or minimum < 1:
            _fail(f"persona_evidence['{name}'].min_markers must be an integer >= 1")
        if minimum > len(expected):
            _fail(
                f"persona_evidence['{name}'] needs {minimum} markers but declares "
                f"only {len(expected)} - the threshold can never be met"
            )
    settings["persona_evidence"] = personas
    settings["version"] = raw.get("version")
    return settings


@lru_cache(maxsize=1)
def get_settings() -> dict[str, Any]:
    return load_settings()
