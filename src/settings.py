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
    "min_pdld_count",
    "address_abbreviations",
)
VALID_REQUIREMENTS = frozenset({"mandatory", "recommended", "optional"})

# Every program must declare these, so that a configuration gap fails on load
# rather than surfacing in the report as a failed criterion for the customer.
REQUIRED_CRITERIA = ("max_cic_group_unsecured", "blwl_blocks_unsecured")


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
    settings["non_core_industries"] = raw.get("non_core_industries") or []
    settings["debt_group_by_label"] = raw.get("debt_group_by_label") or {}
    settings["version"] = raw.get("version")
    return settings


@lru_cache(maxsize=1)
def get_settings() -> dict[str, Any]:
    return load_settings()
