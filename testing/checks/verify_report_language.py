"""The report speaks Vietnamese to a credit reviewer, not Python to a developer.

A word like "pass" or "active" in a Vietnamese sentence reads as neither: the
reviewer cannot tell whether it is a verdict, a step, or a field name. Nine such
strings reached the report before this check existed, four of them in the column a
reviewer reads first.

A denylist, deliberately: the report is full of Vietnamese written without
diacritics ("trong", "danh", "thu"), so an allowlist of ASCII words would either
pass everything or fight the language. What CAN be named exactly is the jargon
this project knows it uses, plus two shapes no business term ever has.
"""

from _harness import ROOT, report
import re
import sys

# Internal vocabulary. Every entry was either found in a rendered report or is a
# term this codebase uses for itself and would be a bug to print.
JARGON = (
    "pass", "config", "checklist", "active", "executor", "verdict", "status",
    "fact", "facts", "prompt", "token", "vault", "mask", "masked", "pipeline",
    "node", "graph", "schema", "payload", "dict", "list", "none", "true", "false",
    "insufficient", "persona_evidence", "llm",
)

# Shapes: snake_case and dotted fact paths. A file name in the dossier is neither
# - it ends in a real extension - so it is let through by name, not by shape.
SNAKE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")
DOTTED = re.compile(r"\b[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]+)+\b")
FILE_EXTENSION = re.compile(r"^\.(xml|pdf|xlsx|xls|docx|doc|jpg|jpeg|png|md|json)\b", re.I)

CASES = (("0201123795", "hồ sơ sạch"), ("0209999999", "hồ sơ ngoài ngưỡng"))


def offences(text: str) -> list[str]:
    found: list[str] = []
    for word in JARGON:
        for hit in re.finditer(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text, re.I):
            # "post-check" is the name of the review itself, not jargon.
            before = text[max(0, hit.start() - 5):hit.start()].lower()
            if word == "check" and before.endswith("post-"):
                continue
            found.append(f"{hit.group(0)!r} in “…{text[max(0, hit.start() - 45):hit.end() + 25]}…”")
            break
    for pattern in (SNAKE, DOTTED):
        for hit in pattern.finditer(text):
            # A word boundary ends before the dot, so the extension that makes this
            # a file name sits just past the match.
            if FILE_EXTENSION.match(text[hit.end():hit.end() + 8]):
                continue
            found.append(f"{hit.group(0)!r} has the shape of an identifier, not a term")
    return found


def main() -> int:
    from src.config import Config
    from src.pipeline import run_postcheck
    from src.tools._executor import sqlite_executor

    database = ROOT / "samples" / "dummy_db" / "postcheck_dummy.sqlite"
    if not database.exists():
        return report(["samples/dummy_db/postcheck_dummy.sqlite is missing; "
                       "run make_dummy_db.py"], "")

    problems: list[str] = []
    measured = 0
    for tax_code, label in CASES:
        result = run_postcheck(
            case_dir=ROOT / "samples" / "case_demo",
            config=Config(query_executor=sqlite_executor(str(database))),
            tax_code=tax_code,
            approval_date="2026-04-01",
            postcheck_date="2026-09-15",
        )
        measured += len(result.report_markdown)
        problems += [f"{label}: {offence}" for offence in offences(result.report_markdown)]

    return report(
        problems,
        f"{measured:,} ký tự báo cáo trên {len(CASES)} hồ sơ: không từ nội bộ nào "
        f"trong {len(JARGON)} từ đã khai, không chuỗi nào có dạng tên biến",
    )


if __name__ == "__main__":
    sys.exit(main())
