"""A prompt rule nobody checks is a suggestion.

The commentary is the only place a model writes into a report somebody signs,
and the template tells it what to do. Telling is not enforcing: the three
failures below are the ones that would actually mislead a reader, and each is
mechanically detectable, so each is detected.

The audit never rewrites the model's prose. A corrected paragraph hides that the
model got it wrong; a paragraph with a note under it does not.
"""

from _harness import report
import sys


def _finding(rule_id: str, status: str, observed: str):
    from src.rules.engine import Finding
    return Finding(
        rule_id=rule_id, title="Tiêu chí kiểm thử", expected="Điều kiện đạt",
        severity="high", status=status, observed=observed,
    )


def main() -> int:
    try:
        from src.report.commentary import audit_commentary
    except ImportError as exc:
        return report([f"commentary.audit_commentary is missing: {exc}"], "")

    findings = [
        _finding("F01", "FAIL", "Bất nhất ở 4/4 trường được đối chiếu"),
        _finding("F02", "PASS", "Không thấy dấu hiệu máy kiểm được trên 3 chứng từ"),
    ]
    problems: list[str] = []

    def _audit(text: str):
        return audit_commentary(text, findings)

    # --- a clean paragraph is left alone -----------------------------------
    clean = (
        "Hồ sơ cho thấy thông tin định danh bất nhất ở 4/4 trường được đối chiếu. "
        "Các dấu hiệu máy kiểm được trên 3 chứng từ không phát hiện bất thường. "
        "Những dấu hiệu cần mắt người vẫn nằm ngoài phạm vi kiểm tự động."
    )
    text, notes = _audit(clean)
    if notes:
        problems.append(f"a valid paragraph was flagged: {notes}")
    if text.strip() != clean.strip():
        problems.append("a valid paragraph was rewritten - the audit must not edit prose")

    # --- a fabricated figure ------------------------------------------------
    _, notes = _audit(
        "Hồ sơ bất nhất ở 4/4 trường. Dư nợ hiện tại là 12.500.000.000 đồng. "
        "Cần rà soát thêm."
    )
    if not any("12" in note for note in notes):
        problems.append(
            "a figure absent from the findings (12.500.000.000) was not flagged - "
            f"notes were {notes}"
        )

    # --- a verdict the table does not carry ---------------------------------
    _, notes = _audit(
        "Hồ sơ bất nhất ở 4/4 trường. Tiêu chí F02 Không đạt. Cần rà soát thêm."
    )
    if not any("F02" in note for note in notes):
        problems.append(
            f"a verdict contradicting the table (F02) was not flagged - notes were {notes}"
        )

    # --- wrong shape ---------------------------------------------------------
    _, notes = _audit("## Nhận định\n\n- Hồ sơ bất nhất ở 4/4 trường.\n- Cần rà soát.")
    if not notes:
        problems.append("a heading and bullet list were not flagged")

    _, notes = _audit("Hồ sơ bất nhất ở 4/4 trường.")
    if not notes:
        problems.append("a one-sentence paragraph was not flagged as too short")

    # --- an empty commentary is not the audit's problem ---------------------
    text, notes = _audit("")
    if notes:
        problems.append("an empty commentary was flagged; there is nothing to audit")

    return report(
        problems,
        "the audit passes a valid paragraph untouched and flags fabricated figures, "
        "invented verdicts, and the wrong shape",
    )


if __name__ == "__main__":
    sys.exit(main())
