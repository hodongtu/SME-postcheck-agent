"""Is a document digitally signed - PRESENCE only, not validity.

Two different questions live behind a digital signature, and this module answers
the first one:

  1. does the file CARRY a signature      <- here
  2. is that signature VALID              <- not here

Presence is decidable by reading structure: an XML filing carries an XMLDSig
<Signature> element, a signed PDF carries a signature dictionary with a
/ByteRange. Validity needs the certificate chain, the trust store and a hash over
the signed bytes, and answering it badly is worse than not answering it - a
report calling a document signed when its signature does not verify is exactly
the assurance nobody should get for free. P05 asks the first question; whoever adds
the second should add a fact of its own rather than widen this one.

Returns True, False, or None. None is not a soft False: it means this format
cannot be judged here (a .docx, an .xlsx), and the caller must keep that apart
from a file that was read and found unsigned.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

XMLDSIG_NAMESPACE = "http://www.w3.org/2000/09/xmldsig#"

# A signed PDF has a signature dictionary, and every such dictionary carries a
# /ByteRange saying which bytes the signature covers. Requiring BOTH a signature
# marker and a /ByteRange keeps an empty signature FIELD - a placeholder a form
# author left for someone to sign later - from reading as a signed document.
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
