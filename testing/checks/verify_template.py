"""The report template is complete, and it accounts for every rule exactly once.

The template is now the report's shape: headings, order, and which criteria sit
under which section all live in src/templates/post-check-template.md rather
than in Python. That buys editability, and it costs the guarantee the parsed
BRD used to give - so the one guarantee worth keeping is asserted here instead.

Every rule must appear under exactly one section of the template. A rule listed
nowhere is a check that runs and is never printed; a rule listed twice is a
finding counted twice in a report somebody signs. Neither is visible by reading
a 100-line Markdown file, which is why a machine reads it.

The other half is the placeholders: a template referring to a value nobody
fills renders a report with a hole in it. Rendering here with the full value
set must leave nothing behind.
"""

from _harness import report
import sys


# Sections that carry a model-written commentary paragraph, and therefore must
# also carry guidance for it.
COMMENTARY_SECTIONS = ("1.2", "1.4")

TEMPLATE_NAME = "post-check-template"


def main() -> int:
    problems: list[str] = []

    try:
        from src.report.templates import TemplateError, load_template
    except ImportError as exc:
        return report(
            [f"src/report/templates.py is not importable: {exc}"],
            "",
        )

    try:
        template = load_template(TEMPLATE_NAME)
    except TemplateError as exc:
        return report([f"{TEMPLATE_NAME} did not load: {exc}"], "")

    from src.rules.registry import RULES

    # --- frontmatter -------------------------------------------------------
    for key in ("name", "description"):
        if not template.metadata.get(key):
            problems.append(f"frontmatter has no '{key}'")
    if template.metadata.get("name") != TEMPLATE_NAME:
        problems.append(
            f"frontmatter name is {template.metadata.get('name')!r}, "
            f"expected {TEMPLATE_NAME!r}"
        )

    # --- every rule placed exactly once ------------------------------------
    known = {rule.id for rule in RULES}
    placed: dict[str, list[str]] = {}
    for section in template.sections():
        for rule_id in template.rules_of(section):
            placed.setdefault(rule_id, []).append(section)

    for rule_id, sections in sorted(placed.items()):
        if rule_id not in known:
            problems.append(f"template lists '{rule_id}', which is not a rule")
        if len(sections) > 1:
            problems.append(
                f"'{rule_id}' appears in {sections} - it would be printed, and "
                f"counted, more than once"
            )
    for rule in RULES:
        if rule.id not in placed:
            problems.append(
                f"'{rule.id}' appears in no section of the template - it is graded "
                f"and then never printed"
            )

    # --- placeholders all have a filler ------------------------------------
    values = {name: f"<{name}>" for name in template.placeholders()}
    rendered = template.render(values)
    leftovers = template.placeholders_in(rendered)
    if leftovers:
        problems.append(f"placeholders survive rendering: {sorted(leftovers)}")
    if "{{" in rendered or "}}" in rendered:
        problems.append("rendered output still contains '{{' or '}}'")

    # --- commentary guidance ----------------------------------------------
    for section in COMMENTARY_SECTIONS:
        guidance = template.guidance(section)
        if not guidance.strip():
            problems.append(
                f"no commentary guidance for section {section} - the model would be "
                f"asked for a paragraph with nothing to write it against"
            )
    # Guidance is instruction for the model, not report content.
    for section in COMMENTARY_SECTIONS:
        if template.guidance(section).strip() and template.guidance(section) in template.body:
            problems.append(
                f"the guidance for {section} is inside the printed body - it would be "
                f"printed into the report"
            )

    return report(
        problems,
        f"{TEMPLATE_NAME}: {len(template.sections())} sections placing "
        f"{len(placed)}/{len(known)} rules exactly once, "
        f"{len(values)} placeholders all filled, guidance for "
        f"{', '.join(COMMENTARY_SECTIONS)}",
    )


if __name__ == "__main__":
    sys.exit(main())
