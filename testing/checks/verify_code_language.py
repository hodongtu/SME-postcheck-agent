"""Code is written in English; only report strings are Vietnamese.

The line this enforces:
  English  - identifiers, comments, docstrings, LLM prompt SCHEMA KEYS,
             fact paths, config keys, internal enum values.
  Vietnamese - Rule.title, Rule.expected, Verdict.observed, status and
             severity labels, fact descriptions, reason strings, report
             headings. All of these are printed for a Vietnamese reviewer.

String literals are therefore NOT scanned: they are exactly where Vietnamese
is allowed - and inside an extraction prompt it is often REQUIRED, because the
model is being told which Vietnamese heading to look for, or which Vietnamese
label to emit. Translating those would break extraction against a document
written in Vietnamese.

What is NOT allowed there is a Vietnamese JSON KEY: keys cross the boundary into
this project's code, so they are asserted separately below. Identifiers, comments and docstrings are, because nothing there
ever reaches the reader.

Both src/ and testing/ are scanned. Code copied from SME_creditmemo is skipped:
it is deliberately not edited here so fixes keep flowing between the projects,
and restyling it would fork the copy.

The exemption is a LIST OF FILES, not a directory prefix. Those trees are no
longer purely vendored - this project has added modules of its own inside them -
and a prefix would exempt work nobody else wrote, which is how a Vietnamese
prompt and a Vietnamese docstring got in unnoticed.
"""

from _harness import ROOT, report
import ast
import io
import sys
import tokenize
import unicodedata


# Copied from SME_creditmemo. Anything under those trees NOT listed here was
# written for this project and is scanned like any other file.
VENDORED_TREES = ("src/agents/", "src/utils/")
OURS_INSIDE_VENDORED = (
    "src/agents/extraction/sitevisit_photo_extraction.py",
    "src/utils/reading/digital_signature.py",
)
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
        vendored = (any(relative.startswith(tree) for tree in VENDORED_TREES)
                    and relative not in OURS_INSIDE_VENDORED)
        if vendored:
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


# Every JSON key the extraction prompts ask the model for. See the check below
# for why this is a list rather than a spelling rule.
EXTRACTION_SCHEMA_KEYS = frozenset({
    "amount", "assumptions", "audit_opinion", "auditor_name", "balance_sheet",
    "business_plan", "business_plan_next_year", "business_profile", "capital_plan",
    "cash_flow_statement", "category", "cogs", "collateral",
    "comparative_period_label", "conclusion", "conditions", "contract_value",
    "credit_request", "customer", "customer_participants", "deferred_days",
    "deferred_share", "depreciation", "description", "document_type", "end_date",
    "extraction_notes", "facilities", "filename", "gross_profit", "gso_code",
    "import_ratio", "income_statement", "industry", "inputs", "interest_expense",
    "interest_method", "is_audited", "item", "item_columns", "items",
    "lc_share_of_import", "lc_terms", "line_items", "loan_capital", "location",
    "main_products", "markers", "method", "name", "narrative", "net_revenue",
    "note", "notes", "officers", "opinion_type", "other_capital", "outputs",
    "overall_assessment", "own_capital", "owner", "page", "period_label", "photos",
    "plan_efficiency", "plan_year", "planned_value", "principal_method", "profit",
    "profit_before_tax", "recommendation", "repayment_plan", "reporting_period",
    "revenue", "risks_noted", "sections", "selling_admin_expense", "sight_days",
    "sight_share", "source_unit", "sources", "start_date", "status", "supplier",
    "supply_chain", "survey_date", "survey_info", "tax_code", "tenor", "terms",
    "title", "total", "total_contract_value", "total_limit", "total_planned_value",
    "total_value", "unit", "value", "year", "years"
})


def prompt_schema_keys() -> list[tuple[str, str, str]]:
    """Every JSON key an extraction prompt asks the model for."""

    import re

    found = []
    for path in sorted((ROOT / "src" / "agents" / "extraction").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for block in re.finditer(r'^([A-Z_]*PROMPT)\s*=\s*"""(.*?)"""', text, re.S | re.M):
            for key in re.findall(r'"([^"\s]+)"\s*:', block.group(2)):
                found.append((path.name, block.group(1), key))
    return found


def main() -> int:
    problems: list[str] = []
    scanned = _scan_source_files(problems)
    facts = _scan_fact_paths(problems)
    # A Vietnamese key would flow straight into pipeline.py and the rules; a
    # Vietnamese VALUE in the same schema is document data and must stay.
    #
    # Checked against a DECLARED LIST, not against a character rule. Vietnamese
    # written without diacritics - "ten", "ma_so_thue", "dau_hieu" - is plain
    # ASCII snake_case and passes every spelling test there is. The only thing
    # that catches it is a human reading the key once, which is what updating
    # this list forces. It is not meant to be stable-forever: when a schema
    # legitimately changes, add the key and look at the language while you do.
    keys = prompt_schema_keys()
    if not keys:
        problems.append(
            "no JSON keys found in any extraction prompt - the scan is broken, and "
            "it would pass silently forever"
        )
    for filename, constant, key in keys:
        if key not in EXTRACTION_SCHEMA_KEYS:
            problems.append(
                f"{filename} :: {constant}: JSON key '{key}' is not in "
                f"EXTRACTION_SCHEMA_KEYS. Add it there, in English - a key crosses "
                f"into this project's code, unlike the Vietnamese values beside it"
            )
    for key in sorted(EXTRACTION_SCHEMA_KEYS - {k for _, _, k in keys}):
        problems.append(
            f"EXTRACTION_SCHEMA_KEYS lists '{key}', which no prompt asks for any more"
        )

    return report(
        problems,
        f"{scanned} authored files under src/ and testing/ are written in English; "
        f"{facts} fact paths are ASCII",
    )


if __name__ == "__main__":
    sys.exit(main())
