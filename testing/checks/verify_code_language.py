"""Code is written in English; only report strings are Vietnamese.

The line this enforces:
  English  - identifiers, comments, docstrings, LLM prompts, JSON keys,
             fact paths, config keys, internal enum values.
  Vietnamese - Rule.title, Rule.expected, Verdict.observed, status and
             severity labels, fact descriptions, reason strings, report
             headings. All of these are printed for a Vietnamese reviewer.

String literals are therefore NOT scanned: they are exactly where Vietnamese
is allowed. Identifiers, comments and docstrings are, because nothing there
ever reaches the reader.

Both src/ and testing/ are scanned. Vendored trees are skipped: src/agents/
and src/utils/ are copied verbatim from SME_creditmemo and deliberately not
edited here, so that fixes can keep flowing between the two projects; editing
them for style would fork the copy.
"""

from _harness import ROOT, report
import ast
import io
import sys
import tokenize
import unicodedata


VENDORED = ("src/agents/", "src/utils/")
FACT_PATH_PATTERN = "abcdefghijklmnopqrstuvwxyz0123456789_."


def _accented_letters(text: str) -> set[str]:
    """Non-ASCII Latin letters, e.g. the diacritics Vietnamese is written with.

    Detected structurally rather than from a character list: a letter counts
    when stripping its combining marks leaves a plain ASCII letter. Typographic
    punctuation (em dash, arrow) is not a letter and passes through, so English
    prose keeps its usual marks.
    """

    found: set[str] = set()
    for char in text:
        if char.isascii() or not char.isalpha():
            continue
        base = unicodedata.normalize("NFD", char)[0]
        if base.isascii() and base.isalpha():
            found.add(char)
        elif char in "đĐ":
            found.add(char)
    return found


def _identifiers(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name)
    return names


def _docstrings(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            text = ast.get_docstring(node)
            if text:
                out.append(text)
    return out


def _comments(source: str) -> list[str]:
    out: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                out.append(token.string)
    except tokenize.TokenError:
        pass
    return out


SCANNED_TREES = ("src", "testing")


def _scan_source_files(problems: list[str]) -> int:
    scanned = 0
    paths = sorted(
        path for tree in SCANNED_TREES for path in (ROOT / tree).rglob("*.py")
    )
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if "__pycache__" in relative:
            continue
        if any(relative.startswith(prefix) for prefix in VENDORED):
            continue
        scanned += 1
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for name in sorted(_identifiers(tree)):
            bad = _accented_letters(name)
            if bad:
                problems.append(f"{relative}: identifier '{name}' uses {sorted(bad)}")

        for text in _docstrings(tree):
            bad = _accented_letters(text)
            if bad:
                first = text.strip().splitlines()[0][:60]
                problems.append(
                    f"{relative}: docstring uses {sorted(bad)[:6]} - \"{first}...\""
                )

        for comment in _comments(source):
            bad = _accented_letters(comment)
            if bad:
                problems.append(
                    f"{relative}: comment uses {sorted(bad)[:6]} - {comment[:60]}"
                )
    return scanned


def _scan_fact_paths(problems: list[str]) -> int:
    from src.facts import FACT_KEYS

    for path in FACT_KEYS:
        if any(char not in FACT_PATH_PATTERN for char in path):
            problems.append(
                f"FACT_KEYS: '{path}' must be lowercase ASCII, digits, '_' and '.'"
            )
    return len(FACT_KEYS)


def main() -> int:
    problems: list[str] = []
    scanned = _scan_source_files(problems)
    facts = _scan_fact_paths(problems)
    return report(
        problems,
        f"{scanned} authored files under src/ and testing/ are written in English; "
        f"{facts} fact paths are ASCII",
    )


if __name__ == "__main__":
    sys.exit(main())
