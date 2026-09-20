"""The persona table, the vision vocabulary and V10 agree with one another.

V10 is the only criterion whose evidence comes from a photograph, and it is the
one place where a model's output is counted rather than read. That makes three
joints worth holding, none of which any other check touches:

  1. Every persona declares markers it could actually meet. A threshold above the
     number of markers declared makes V10 fail every customer of that persona -
     and the report would look completely ordinary while it happened.
  2. The vocabulary handed to the model is EXACTLY the union of every persona's
     markers. Drop one and the model can never report it; add one and it reports
     something no persona counts. Either way the vision half and the grading half
     are speaking different languages.
  3. The model is not told which persona it is confirming. The vocabulary is the
     whole union precisely so it cannot be, and that is asserted here rather than
     left to a comment somebody may later "simplify".

A fourth joint sits below those: most dossiers deliver their photographs as ONE
PDF rather than as loose files, and most pages of such a PDF hold SEVERAL photos
pasted together. So the pass has to split a document into images two different
ways - a page at a time, or a photograph at a time where the page is a collage.
Both are asserted here, against sample PDFs, with no model involved: a pass that
silently reads only the first page of a twelve-page dossier, or hands the model
one flattened page where four photographs were, would still look like it worked.

V10 itself is graded from facts built here, so this runs with no model, no
network and no database - like the other 40 criteria.
"""

from _harness import ROOT, report
import sys


def _facts(persona, is_site_visit, photos):
    from src.facts import Facts

    facts = Facts()
    facts.set("los.persona", persona)
    facts.set("los.is_site_visit", is_site_visit)
    if photos is not None:
        facts.set("doc.sitevisit_photo_evidence", photos)
    return facts


def main() -> int:
    from src.agents.extraction.sitevisit_photo_extraction import photo_vocabulary
    from src.rules.identity import check_persona_photos
    from src.settings import get_settings
    from src.utils.common import normalize_text

    settings = get_settings()
    personas = settings.get("persona_evidence") or {}
    problems: list[str] = []

    if not personas:
        return report(["persona_evidence is empty - V10 can never be graded"], "")

    # --- 1: every persona can meet its own threshold ------------------------
    for name, entry in personas.items():
        expected = (entry or {}).get("expected") or []
        minimum = (entry or {}).get("min_markers")
        if not expected or not isinstance(minimum, int) or minimum < 1:
            problems.append(f"persona {name!r}: markers {expected!r}, min {minimum!r}")
        elif minimum > len(expected):
            problems.append(
                f"persona {name!r} needs {minimum} markers but declares {len(expected)} "
                f"- V10 would fail every customer of this persona"
            )
        if len(expected) != len({normalize_text(m) for m in expected}):
            problems.append(f"persona {name!r} declares the same marker twice")

    # --- 2 and 3: the vocabulary is the whole union, no more and no less -----
    union = {normalize_text(marker)
             for entry in personas.values()
             for marker in (entry or {}).get("expected") or []}
    vocabulary = {normalize_text(marker) for marker in photo_vocabulary(settings)}
    for marker in sorted(union - vocabulary):
        problems.append(
            f"marker {marker!r} is expected by a persona but absent from the vision "
            f"vocabulary - the model can never report it, so it is uncountable"
        )
    for marker in sorted(vocabulary - union):
        problems.append(
            f"the vision vocabulary offers {marker!r}, which no persona expects - the "
            f"model can report something nothing grades"
        )
    for name, entry in personas.items():
        own = {normalize_text(m) for m in (entry or {}).get("expected") or []}
        if own and vocabulary == own and len(personas) > 1:
            problems.append(
                f"the vocabulary equals persona {name!r}'s own markers - the model is "
                f"being told which persona to confirm"
            )

    # --- V10 decides, and decides from the facts ----------------------------
    name, entry = next(iter(personas.items()))
    markers = list(entry["expected"])
    minimum = int(entry["min_markers"])

    enough = _facts(name, True, [{"filename": "a.jpg", "markers": markers[:minimum]}])
    verdict = check_persona_photos(enough, settings)
    if verdict.status != "PASS":
        problems.append(f"{minimum} markers met the threshold of {minimum} yet V10 "
                        f"returned {verdict.status}: {verdict.observed}")

    if minimum > 0:
        short = _facts(name, True, [{"filename": "a.jpg", "markers": markers[:minimum - 1]}])
        verdict = check_persona_photos(short, settings)
        if verdict.status != "FAIL":
            problems.append(f"{minimum - 1} markers is below the threshold of "
                            f"{minimum} yet V10 returned {verdict.status}")

    off_topic = _facts(name, True, [{"filename": "a.jpg", "markers": ["mot nhan la"]}])
    if check_persona_photos(off_topic, settings).status != "FAIL":
        problems.append("a photo showing nothing the persona expects did not fail V10")

    # No site visit asked for: V10 passes, and does so WITHOUT any photo fact.
    no_visit = _facts(name, False, None)
    verdict = check_persona_photos(no_visit, settings)
    if verdict.status != "PASS":
        problems.append(
            f"LOS asked for no site visit, yet V10 returned {verdict.status} - a "
            f"review that correctly needs no photos must not read as a gap"
        )

    unknown = _facts("mot chan dung chua khai", True, [{"filename": "a.jpg", "markers": []}])
    if check_persona_photos(unknown, settings).status != "FAIL":
        problems.append("a persona absent from the table did not fail V10")

    # --- a photo PDF becomes one image per page ----------------------------
    from src.agents.extraction.sitevisit_photo_extraction import (
        _images_from_file,
        _image_count,
    )

    photo_pdf = (ROOT / "samples" / "case_demo" / "ho_so_soan_thao_noi_bo"
                 / "anh_khao_sat_thuc_dia_tong_hop.pdf")
    photo_jpg = (ROOT / "samples" / "case_demo" / "ho_so_soan_thao_noi_bo"
                 / "anh_khao_sat_thuc_dia_1.jpg")

    pages = _image_count(str(photo_pdf))
    if pages < 2:
        problems.append(
            f"the sample photo PDF has {pages} page(s) - a single-page fixture cannot "
            f"show that every page is read, which is the whole point of this branch"
        )
    rendered = _images_from_file(str(photo_pdf), 12)
    if len(rendered) != pages:
        problems.append(
            f"the photo PDF has {pages} pages but rendered {len(rendered)} images - "
            f"pages are being lost before the model ever sees them"
        )
    if len({label for label, _, _ in rendered}) != len(rendered):
        problems.append("two rendered pages share a label - the model cannot tell "
                        "which page an entry belongs to")

    capped = _images_from_file(str(photo_pdf), 1)
    if len(capped) != 1:
        problems.append(f"max_images=1 still produced {len(capped)} images")

    # --- a collage page becomes one image PER PHOTOGRAPH --------------------
    collage_pdf = (ROOT / "samples" / "case_demo" / "ho_so_soan_thao_noi_bo"
                   / "anh_khao_sat_thuc_dia_ghep_trang.pdf")
    collage = _images_from_file(str(collage_pdf), 12)
    if len(collage) < 4:
        problems.append(
            f"the one-page collage fixture yielded {len(collage)} image(s), expected "
            f"its 4 photographs - a flattened page hands the model a quarter of the "
            f"resolution and one answer where there should be four"
        )
    if len({label for label, _, _ in collage}) != len(collage):
        problems.append("two photographs from the collage share a label")
    if collage and not all("ảnh" in label for label, _, _ in collage):
        problems.append(
            "a collage image is labelled as a whole page - the label must say which "
            "photograph on the page it is"
        )
    # The page also carries a company logo, as these pages always do. It is an
    # embedded image like the photographs, and the size floor is the only thing
    # keeping it from being read as a picture of the business.
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(collage_pdf))
    try:
        embedded = sum(1 for obj in document[0].get_objects()
                       if isinstance(obj, pdfium.PdfImage))
    finally:
        document.close()
    if embedded <= len(collage):
        problems.append(
            f"the collage page has {embedded} embedded images and {len(collage)} were "
            f"kept - nothing was rejected, so the size floor that keeps logos and "
            f"rules out of the evidence is untested"
        )

    if _image_count(str(collage_pdf)) != len(collage):
        problems.append(
            f"_image_count says {_image_count(str(collage_pdf))} but "
            f"{len(collage)} were produced - the truncation note would lie"
        )

    loose = _images_from_file(str(photo_jpg), 12)
    if len(loose) != 1:
        problems.append(f"a single JPEG rendered {len(loose)} images, expected 1")

    not_an_image = (ROOT / "samples" / "case_demo" / "ho_so_tai_chinh"
                    / "bao_cao_tai_chinh_2025.xml")
    if _images_from_file(str(not_an_image), 12):
        problems.append("a non-image, non-PDF file produced images - the pass would "
                        "send the model something that is not a photograph")

    return report(
        problems,
        f"{len(personas)} personas, each able to meet its own threshold; the vision "
        f"vocabulary is exactly the {len(union)}-marker union of all of them; V10 "
        f"passes at the threshold, fails below it, and passes without photos when "
        f"LOS asks for no site visit; the {pages}-page sample PDF renders one image "
        f"per page and honours the ceiling, and the collage page splits into its "
        f"{len(collage)} separate photographs",
    )


if __name__ == "__main__":
    sys.exit(main())
