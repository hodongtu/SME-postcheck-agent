"""Read src/templates/*.md: the report's shape, kept out of Python. """

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.utils.paths import PROJECT_ROOT


TEMPLATE_DIR = PROJECT_ROOT / "src" / "templates"

GUIDANCE_MARKER = "<!--GUIDANCE-->"

_PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_]+(?::[A-Za-z0-9_.]+)?)\}\}")
_RULES_MARKER = re.compile(r"<!--\s*rules:\s*([^>]*?)\s*-->")
_GUIDANCE_BLOCK = re.compile(r"^##\s+(\S+)\s*$", re.M)


class TemplateError(RuntimeError):
    """The template is missing or malformed."""


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Separate Agent-Skills style YAML frontmatter from the body.

    Same shape as SME_creditmemo's SpecialistAgent._split_frontmatter, so a
    template can move between the two projects unchanged.
    """

    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if not line.strip() or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        metadata[key.strip()] = value.strip()
    return metadata, parts[2].lstrip("\n")


@dataclass(frozen=True)
class Template:
    """One report template: the printed body, plus what drives it."""

    name: str
    metadata: dict[str, str]
    body: str                       # what gets printed, placeholders unfilled
    _guidance: str                  # prompt material, never printed

    # -- placeholders -------------------------------------------------------

    @staticmethod
    def placeholders_in(text: str) -> set[str]:
        return set(_PLACEHOLDER.findall(text))

    def placeholders(self) -> tuple[str, ...]:
        """Every placeholder the body asks for, in order of first appearance."""

        seen: list[str] = []
        for name in _PLACEHOLDER.findall(self.body):
            if name not in seen:
                seen.append(name)
        return tuple(seen)

    def render(self, values: dict[str, str]) -> str:
        """Fill the body. An unfilled placeholder is an error, not a blank. """

        missing = [name for name in self.placeholders() if name not in values]
        if missing:
            raise TemplateError(
                f"{self.name}: nothing to fill {missing} with. Either the template "
                f"asks for a value the renderer does not produce, or a value was "
                f"renamed on one side only."
            )
        rendered = _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), self.body)
        rendered = _RULES_MARKER.sub("", rendered)
        return re.sub(r"\n{3,}", "\n\n", rendered).strip() + "\n"

    # -- rule placement -----------------------------------------------------

    def sections(self) -> tuple[str, ...]:
        """Section keys that carry a criteria table, in template order."""

        return tuple(
            name.split(":", 1)[1]
            for name in self.placeholders()
            if name.startswith("BangTieuChi:")
        )

    def rules_of(self, section: str) -> tuple[str, ...]:
        """Rule ids declared for a section by its <!-- rules: ... --> marker. """

        anchor = self.body.find(f"{{{{BangTieuChi:{section}}}}}")
        if anchor < 0:
            return ()
        markers = list(_RULES_MARKER.finditer(self.body, 0, anchor))
        if not markers:
            return ()
        return tuple(markers[-1].group(1).split())

    # -- commentary guidance ------------------------------------------------

    def guidance(self, section: str) -> str:
        """The guidance block for one section, plus the shared one."""

        blocks = self._guidance_blocks()
        parts = [blocks.get("chung", ""), blocks.get(section, "")]
        return "\n\n".join(part.strip() for part in parts if part.strip())

    def _guidance_blocks(self) -> dict[str, str]:
        blocks: dict[str, str] = {}
        headings = list(_GUIDANCE_BLOCK.finditer(self._guidance))
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(self._guidance)
            blocks[heading.group(1)] = self._guidance[heading.end():end].strip()
        return blocks


def load_template(name: str) -> Template:
    """Read one template by name, splitting frontmatter, body and guidance."""

    path = TEMPLATE_DIR / f"{name}.md"
    if not path.is_file():
        raise TemplateError(f"no template at {path}")

    metadata, text = split_frontmatter(path.read_text(encoding="utf-8"))
    if not metadata:
        raise TemplateError(f"{path} has no frontmatter")

    body, _, guidance = text.partition(GUIDANCE_MARKER)
    return Template(name=name, metadata=metadata, body=body.strip() + "\n",
                    _guidance=guidance)


@lru_cache(maxsize=4)
def get_template(name: str) -> Template:
    return load_template(name)
