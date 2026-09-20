"""Digital-signature detection answers three states, and never guesses the third.

P05 asks whether the statements carry a digital signature. The detector reads
structure - an XMLDSig element, a PDF signature dictionary - so it costs nothing
and is exact where it applies. What it must never do is turn "I cannot read this
format" into "unsigned": that would report a finding against a customer on the
strength of a .docx nobody parsed.

So three states are asserted here, not two, and the PDF half is asserted against
bytes crafted in this file rather than a sample - a genuinely signed PDF cannot
be committed to this repository, and a structural fixture tests the structural
check honestly.
"""

from _harness import ROOT, report
import sys
import tempfile
from pathlib import Path


XML_SIGNED = ROOT / "samples" / "case_demo" / "ho_so_tai_chinh" / "bao_cao_tai_chinh_2025.xml"
PDF_UNSIGNED = (ROOT / "samples" / "case_demo" / "ho_so_soan_thao_noi_bo"
                / "bao_cao_khao_sat_thuc_dia.pdf")
XLSX_UNJUDGEABLE = (ROOT / "samples" / "case_demo" / "ho_so_tai_chinh"
                    / "bang_can_doi_ke_toan_2025.xlsx")

# A signature dictionary as a signed PDF carries it: the /ByteRange saying what
# is covered, and the marker naming the signature type.
PDF_WITH_SIGNATURE = (
    b"%PDF-1.7\n"
    b"1 0 obj<</Type/Sig/Filter/Adobe.PPKLite/SubFilter/adbe.pkcs7.detached"
    b"/ByteRange[0 840 960 1200]/Contents<308006>>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
# A signature dictionary PREPARED BUT NEVER SIGNED: it names itself /Type/Sig,
# so the marker alone would call it signed, but it carries no /ByteRange because
# nothing has been covered yet. This is the case the /ByteRange condition exists
# for, and the fixture is written so that removing that condition turns this
# green-to-red.
PDF_EMPTY_FIELD = (
    b"%PDF-1.7\n"
    b"1 0 obj<</Type/Sig/Filter/Adobe.PPKLite/SubFilter/adbe.pkcs7.detached>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def main() -> int:
    from src.utils.reading.digital_signature import has_digital_signature

    problems: list[str] = []
    scratch = Path(tempfile.mkdtemp())

    signed_pdf = scratch / "signed.pdf"
    signed_pdf.write_bytes(PDF_WITH_SIGNATURE)
    empty_field_pdf = scratch / "empty_field.pdf"
    empty_field_pdf.write_bytes(PDF_EMPTY_FIELD)

    cases = (
        ("XMLDSig in the e-tax filing", XML_SIGNED, True),
        ("a PDF carrying a signature dictionary", signed_pdf, True),
        ("a signature dictionary nobody signed", empty_field_pdf, False),
        ("a PDF with no signature at all", PDF_UNSIGNED, False),
        ("a format this cannot judge", XLSX_UNJUDGEABLE, None),
        ("a file that does not exist", scratch / "absent.pdf", None),
    )
    for label, path, expected in cases:
        got = has_digital_signature(path)
        if got is not expected:
            problems.append(f"{label}: got {got!r}, expected {expected!r} ({path.name})")

    # The three states must stay three. A detector that returned False instead of
    # None for an unreadable format would make P05 fail customers over a file
    # nobody parsed, and the pipeline could not tell the two apart.
    if has_digital_signature(XLSX_UNJUDGEABLE) is False:
        problems.append(
            "an unjudgeable format returned False - 'cannot read' collapsed into "
            "'unsigned', which is a finding drawn from no evidence"
        )

    return report(
        problems,
        f"{len(cases)} cases: XMLDSig and a PDF signature dictionary read as signed, "
        f"an unsigned dictionary and a plain PDF as unsigned, and an unreadable format "
        f"as unknown rather than unsigned",
    )


if __name__ == "__main__":
    sys.exit(main())
