"""Comparison helpers for the identity and consistency rules.

Matching is exact after normalisation, deliberately. Fuzzy similarity was
considered and rejected: a 0.85 threshold is a number nobody can defend to a
credit committee, and a near-miss on a tax code is not a near-miss.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from src.utils.common import normalize_text


_NON_DIGIT = re.compile(r"\D+")
_TOKEN_SPLIT = re.compile(r"[^0-9a-z]+")


def norm_text(value: Any) -> str:
    """Strip diacritics, lowercase, collapse whitespace."""

    return normalize_text(str(value or "")).strip()


def norm_digits(value: Any) -> str:
    """Digits only. For tax codes and ID numbers, where separators are noise."""

    return _NON_DIGIT.sub("", str(value or ""))


def norm_year(value: Any) -> str:
    """A birth year: the first four-digit year, so 1980 and 01/01/1980 match."""

    match = re.search(r"(1[89]\d{2}|20\d{2})", str(value or ""))
    return match.group(1) if match else norm_digits(value)


def make_address_normalizer(abbreviations: dict[str, str]) -> Callable[[Any], str]:
    """Normalise an address, expanding the abbreviations declared in programs.yaml."""

    def normalize(value: Any) -> str:
        tokens = [token for token in _TOKEN_SPLIT.split(norm_text(value)) if token]
        return " ".join(abbreviations.get(token, token) for token in tokens)

    return normalize


def industry_matches(left: Any, right: Any) -> bool:
    """Two industry descriptions match when equal, or one contains the other.

    Industry is written at different levels of detail depending on the
    document: BEP returns one short line, the business registration lists every
    registered activity. Containment is the strictest test that still works.
    """

    first, second = norm_text(left), norm_text(right)
    if not first or not second:
        return False
    return first == second or first in second or second in first


def rows(values: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    """[{'filename': f, 'value': v}, ...] -> [(f, v), ...], dropping empty cells."""

    out: list[tuple[str, Any]] = []
    for row in values:
        value = row.get("value")
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        out.append((str(row.get("filename", "?")), value))
    return out


def distinct(
    pairs: list[tuple[str, Any]], normalizer: Callable[[Any], str]
) -> dict[str, tuple[Any, list[str]]]:
    """Group by normalised value. More than one key means the dossier disagrees.

    Each group keeps the first value as printed: the report must quote what the
    document actually says, not the accent-stripped form used for matching.
    """

    groups: dict[str, tuple[Any, list[str]]] = {}
    for filename, value in pairs:
        key = normalizer(value)
        if key in groups:
            groups[key][1].append(filename)
        else:
            groups[key] = (value, [filename])
    return groups
