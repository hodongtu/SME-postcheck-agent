"""Is a document digitally signed - PRESENCE only, not validity. """

from pathlib import Path
from xml.etree import ElementTree

XMLDSIG_NAMESPACE = "http://www.w3.org/2000/09/xmldsig#"

PDF_SIGNATURE_MARKERS = (b"/Type/Sig", b"/Type /Sig", b"adbe.pkcs7", b"ETSI.CAdES")

JUDGEABLE_EXTENSIONS = frozenset({".xml", ".pdf"})


def _xml_is_signed(path: Path) -> bool | None:
    try:
        tree = ElementTree.parse(path)
    except (ElementTree.ParseError, OSError):
        return None
    return any(
        element.tag == f"{{{XMLDSIG_NAMESPACE}}}Signature"
        for element in tree.iter()
    )


def _pdf_is_signed(path: Path) -> bool | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"/ByteRange" not in data:
        return False
    return any(marker in data for marker in PDF_SIGNATURE_MARKERS)


def has_digital_signature(file_path: str | Path) -> bool | None:
    """True, False, or None when the format cannot be judged here."""

    path = Path(file_path)
    extension = path.suffix.lower()
    if extension == ".xml":
        return _xml_is_signed(path)
    if extension == ".pdf":
        return _pdf_is_signed(path)
    return None
