"""The two commentary paragraphs - the only prose a model writes into the report. """

import re
from typing import Any

from src.report.templates import get_template
from src.rules.engine import Finding


TEMPLATE_NAME = "post-check-template"

MIN_SENTENCES = 3
MAX_SENTENCES = 6

_NUMBER = re.compile(r"\d[\d.,]*")
_RULE_ID = re.compile(r"\b([VFPCOE]\d\d)\b")
_HEADING = re.compile(r"^#{1,6}\s", re.M)
_BULLET = re.compile(r"^\s*[-*+]\s|^\s*\d+[.)]\s", re.M)
_SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")
_VERDICT_WORDS = ("không đạt", "thiếu dữ liệu", "đạt")


def _digits(text: str) -> str:
    """A figure reduced to its digits, so 40%, 40.0 and 40 compare equal."""

    return re.sub(r"\D", "", text).lstrip("0") or "0"


def audit_commentary(text: str, findings: list[Finding]) -> tuple[str, list[str]]:
    """The commentary as it will be printed, plus what it broke.

    Never edits the prose. A silently corrected paragraph hides that the model
    got it wrong, and the next reader has no way to know it happened.
    """

    text = (text or "").strip()
    if not text:
        return text, []

    notes: list[str] = []
    source = " ".join(
        [finding.observed for finding in findings]
        + [finding.title for finding in findings]
    )
    known_numbers = {_digits(match) for match in _NUMBER.findall(source)}

    without_ids = _RULE_ID.sub(" ", text)
    invented = sorted(
        {match for match in _NUMBER.findall(without_ids)
         if _digits(match) not in known_numbers}
    )
    if invented:
        notes.append(
            "nêu con số không có trong các kết luận được đưa vào: "
            + ", ".join(invented)
        )

    status_by_rule = {finding.rule_id: finding.status_label.lower() for finding in findings}
    lowered = text.lower()
    for rule_id in sorted(set(_RULE_ID.findall(text))):
        if rule_id not in status_by_rule:
            notes.append(f"nhắc tới mã tiêu chí {rule_id} không có trong mục này")
            continue
        position = lowered.find(rule_id.lower())
        nearby = lowered[position: position + 80]
        claimed = next((word for word in _VERDICT_WORDS if word in nearby), "")
        if claimed and claimed != status_by_rule[rule_id]:
            notes.append(
                f"gán cho {rule_id} một kết luận khác với bảng "
                f"(bảng ghi: {status_by_rule[rule_id]})"
            )

    if _HEADING.search(text):
        notes.append("có tiêu đề, trong khi phần nhận định phải là một đoạn liền mạch")
    if _BULLET.search(text):
        notes.append("có gạch đầu dòng, trong khi phần nhận định phải là một đoạn liền mạch")

    sentences = len([part for part in _SENTENCE_END.split(text) if part.strip()])
    if not MIN_SENTENCES <= sentences <= MAX_SENTENCES:
        notes.append(
            f"dài {sentences} câu, ngoài khoảng {MIN_SENTENCES}–{MAX_SENTENCES} câu"
        )

    return text, notes


def _describe(findings: list[Finding]) -> str:
    return "\n".join(
        f"- [{f.rule_id}] {f.title} — {f.status_label} (mức độ {f.severity_label}): {f.observed}"
        for f in findings
    )


def build_commentary(
    findings: list[Finding],
    llm: Any,
    sections: tuple[str, ...] = ("2.2", "2.4"),
) -> dict[str, str]:
    """One paragraph per section. With no LLM it returns empty, and the report
    still renders with a note in place of each paragraph."""

    if llm is None:
        return {}

    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    template = get_template(TEMPLATE_NAME)
    by_id = {finding.rule_id: finding for finding in findings}
    out: dict[str, str] = {}

    for section in sections:
        rows = [by_id[rule_id] for rule_id in template.rules_of(section) if rule_id in by_id]
        if not rows:
            continue

        chain = (
            ChatPromptTemplate.from_messages([
                ("system", template.guidance(section)),
                ("human", "Mục {section}. Các kết luận đã chốt:\n\n{findings}"),
            ])
            | llm
            | StrOutputParser()
        )
        try:
            written = chain.invoke({"section": section, "findings": _describe(rows)})
        except Exception as exc:                 
            out[section] = (
                f"_Chưa sinh được nhận định cho mục này: {type(exc).__name__}: {exc}_"
            )
            continue

        text, notes = audit_commentary(written, rows)
        if notes:
            text += "\n\n" + "\n".join(
                f"> _Ghi chú kiểm soát: đoạn nhận định trên {note}._" for note in notes
            )
        out[section] = text

    return out
