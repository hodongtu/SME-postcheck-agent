"""Load and validate config/programs.yaml. """

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
VALID_CONDITIONS = frozenset({"site_visit"})

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
    for key in ("focus_GSO", "restricted_GSO"):
        settings[key] = [
            str(code).strip() for code in (raw.get(key) or []) if str(code or "").strip()
        ]
    settings["debt_group_by_label"] = raw.get("debt_group_by_label") or {}
    settings["financial_report_types"] = raw.get("financial_report_types") or {}

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
