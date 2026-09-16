"""Shared bootstrap for the check scripts."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "testing" / "fixtures"


def load_fixture(name: str):
    from src.facts import Facts
    return Facts.from_json_file(str(FIXTURES / f"{name}.json"))


def report(problems: list[str], ok_message: str) -> int:
    if problems:
        for line in problems:
            print(f"  x {line}")
        return 1
    print(f"  ok {ok_message}")
    return 0
