"""Label what a site-visit photograph shows - the ONLY vision pass in the project.

Two rules shape this module, and both exist to keep the verdict out of the model:

  1. It LABELS, it does not judge. The model is asked which of a fixed list of
     things appear in the photo. Whether that matches the customer's declared
     persona is decided by check_persona_photos in src/rules/identity.py, from
     the facts this produces - which is what keeps V10 testable from a JSON
     fixture with no model and no network, like the other criteria.

  2. It is never told the answer. The vocabulary handed to the model is the
     UNION of every persona's expected markers, not the customer's own list.
     Passing the expected list would be asking the model to confirm what we
     already hope to see, and a vision model is very willing to oblige.

Labels outside the vocabulary are dropped and recorded in extraction_notes, so a
word the model invented cannot quietly become evidence a criterion counts.
"""

from __future__ import annotations

import base64
import io
import mimetypes
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.common import normalize_text

REQUIRED_TOP_LEVEL_KEYS = {"photos"}

SITEVISIT_PHOTO_SYSTEM_PROMPT = """
You label photographs taken by a relationship manager during a site visit to a
corporate customer's premises.

You are given ONE OR MORE photographs and a CLOSED VOCABULARY of things that may
appear in them. Each image is announced by a label before it. Report one entry
per image, in the order given, and report only what you can actually see.

A photo dossier usually arrives as a single PDF, and the images you are given may
be whole pages or single photographs cut out of a page - the label says which. A
cover sheet, a blank, or a page of text is a correct empty answer; never carry a
marker over from a neighbouring image.

RULES:
- Use ONLY labels from the vocabulary. Never invent one, never translate one, and
  never return a near-synonym - copy the label exactly as listed.
- A label belongs in the list only if the thing is VISIBLE in this photograph. Do
  not infer it from context, from a sign, or from what a business like this
  usually has.
- An empty list is a correct and useful answer for a photo that shows none of
  them - a car park, a doorway, a portrait.
- "description" is one short sentence describing the scene, for a reviewer who
  has not opened the file. Write it in Vietnamese: it is printed verbatim into a
  Vietnamese report. Everything else about this answer is English.

Answer with EXACTLY this JSON and no other text:
{{
  "photos": [
    {{
      "filename": "the image label you were given, copied exactly",
      "markers": ["label from the vocabulary", "..."],
      "description": "one sentence, in Vietnamese, describing the scene"
    }}
  ]
}}

VOCABULARY:
{vocabulary}
"""


def photo_vocabulary(settings: dict) -> list[str]:
    """Every marker any persona expects, de-duplicated and ordered.

    The union, deliberately. See this module's docstring for why the customer's
    own persona is withheld from the prompt.
    """

    markers = {
        marker
        for entry in (settings.get("persona_evidence") or {}).values()
        for marker in (entry or {}).get("expected") or []
    }
    return sorted(markers)


def build_sitevisit_photo_extraction_chain(llm: Any) -> Any:
    """The 'chain' here is the model itself: images do not go through a text prompt."""

    return llm


PHOTO_PAGE_DPI = 150

MIN_COLLAGE_PHOTOS = 2

MIN_EMBEDDED_PHOTO_PX = 200


def _images_from_file(path: str, max_images: int) -> list[tuple[str, str, str]]:
    """(label, media type, base64) for every image this file carries. """

    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _pdf_images(file_path, max_images)

    media_type = mimetypes.guess_type(file_path.name)[0] or ""
    if not media_type.startswith("image/"):
        return []
    try:
        return [(file_path.name, media_type,
                 base64.b64encode(file_path.read_bytes()).decode("ascii"))]
    except OSError:
        return []


def conform_photo_result(
    result: dict[str, Any], filename: str, vocabulary: list[str]
) -> dict[str, Any]:
    """Keep only labels the vocabulary knows; record the rest rather than dropping them."""

    allowed = {normalize_text(marker): marker for marker in vocabulary}
    notes: list[str] = []
    photos = []
    for entry in result.get("photos") or []:
        if not isinstance(entry, dict):
            continue
        kept, unknown = [], []
        for label in entry.get("markers") or []:
            canonical = allowed.get(normalize_text(str(label)))
            (kept if canonical else unknown).append(canonical or str(label))
        if unknown:
            notes.append(
                f"{filename}: bỏ {len(unknown)} nhãn ngoài từ vựng - "
                + ", ".join(sorted(set(unknown)))
            )
        photos.append({
            "filename": entry.get("filename") or filename,
            "markers": sorted(set(kept)),
            "description": str(entry.get("description") or "").strip(),
        })
    return {"photos": photos, "extraction_notes": notes}


def _as_jpeg(image: Any, label: str) -> tuple[str, str, str]:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=80)
    return label, "image/jpeg", base64.b64encode(buffer.getvalue()).decode("ascii")


def _collage_photos(page: Any) -> list[Any]:
    """The embedded photographs on one page, in reading order, or [] if not a collage."""

    import pypdfium2 as pdfium

    found = []
    for obj in page.get_objects():
        if not isinstance(obj, pdfium.PdfImage):
            continue
        try:
            width, height = obj.get_px_size()
        except Exception:                             # noqa: BLE001
            continue
        if min(width, height) >= MIN_EMBEDDED_PHOTO_PX:
            found.append(obj)

    if len(found) < MIN_COLLAGE_PHOTOS:
        return []
    return sorted(found, key=lambda o: (-o.get_bounds()[3], o.get_bounds()[0]))


def _pdf_images(file_path: Path, limit: int) -> list[tuple[str, str, str]]:
    """Every image a PDF carries, capped at `limit`, newest page last.

    A collage page contributes one image per photograph; any other page
    contributes the rendered page. The label says which, so a reviewer opening
    the file knows where to look.
    """

    import pypdfium2 as pdfium

    from src.utils.reading.ocr import _render_pdf_pages

    images: list[tuple[str, str, str]] = []
    try:
        document = pdfium.PdfDocument(str(file_path))
    except Exception:                                 # noqa: BLE001
        return []
    try:
        for number in range(len(document)):
            if len(images) >= limit:
                break
            page = document[number]
            photos = _collage_photos(page)
            if photos:
                for index, obj in enumerate(photos, start=1):
                    if len(images) >= limit:
                        break
                    try:
                        picture = obj.get_bitmap().to_pil()
                    except Exception:                 # noqa: BLE001
                        continue
                    images.append(_as_jpeg(
                        picture,
                        f"{file_path.name} (trang {number + 1}, ảnh {index})",
                    ))
                continue
            try:
                rendered = _render_pdf_pages(str(file_path), PHOTO_PAGE_DPI, number, 1)
            except Exception:                         # noqa: BLE001
                continue
            if rendered:
                images.append(_as_jpeg(
                    rendered[0], f"{file_path.name} (trang {number + 1})"
                ))
    finally:
        document.close()
    return images


def extract_sitevisit_photo_data(
    chain: Any,
    filename: str,
    content: str,
    path: str = "",
    vocabulary: list[str] | None = None,
    max_images: int = 12,
) -> tuple[dict[str, Any] | None, str]:
    """Send every image this file carries to the vision model. Never raises.

    `content` is ignored: an image has no extracted text, which is exactly why
    this pass is declared `reads_file` and receives `path`.

    ONE call per document, however many images it holds - they travel together in
    a single message. `max_images` bounds the payload; anything beyond it is
    counted in the notes rather than dropped in silence.
    """

    if chain is None:
        return None, "chưa cấu hình mô hình đọc ảnh khảo sát thực địa"
    if not vocabulary:
        return None, "cấu hình hệ thống chưa khai dấu hiệu kỳ vọng của chân dung nào"

    images = _images_from_file(path, max_images)
    if not images:
        return None, f"không đọc được ảnh nào trong '{filename}'"

    parts: list[dict[str, Any]] = []
    for label, media_type, data in images:
        parts.append({"type": "text", "text": f"Image label: {label}"})
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:{media_type};base64,{data}"}})

    messages = [
        SystemMessage(content=SITEVISIT_PHOTO_SYSTEM_PROMPT.format(
            vocabulary="\n".join(f"- {marker}" for marker in vocabulary)
        )),
        HumanMessage(content=parts),
    ]
    try:
        answer = chain.invoke(messages)
    except Exception as exc:                          # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"[:300]

    import json
    text = getattr(answer, "content", answer)
    if isinstance(text, list):
        text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
    try:
        parsed = json.loads(str(text).strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
    except ValueError as exc:
        return None, f"mô hình trả về JSON không hợp lệ: {exc}"[:300]
    if not isinstance(parsed, dict) or "photos" not in parsed:
        return None, "mô hình trả về thiếu khoá 'photos'"

    conformed = conform_photo_result(parsed, filename, vocabulary)
    truncated = _image_count(path) - len(images)
    if truncated > 0:
        conformed["extraction_notes"].append(
            f"{filename}: bỏ qua {truncated} ảnh cuối vì vượt trần {max_images} ảnh"
        )
    return conformed, ""


def _image_count(path: str) -> int:
    """How many images the file really holds, to report what was left out.

    Counted the same way `_pdf_images` builds them - a collage page counts its
    photographs, any other page counts one - so the truncation note says how many
    images were skipped, not how many pages.
    """

    if Path(path).suffix.lower() != ".pdf":
        return 1

    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(path)
    except Exception:                                 # noqa: BLE001
        return 0
    try:
        return sum(len(_collage_photos(document[n])) or 1 for n in range(len(document)))
    finally:
        document.close()
