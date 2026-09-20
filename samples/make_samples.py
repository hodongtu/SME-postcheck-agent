"""Build the sample dossiers. Run: python3 samples/make_samples.py

Two cases, each exercising a different part of the pipeline:

  case_demo        a complete B1CP dossier: all eight mandatory checklist
                   items, permitted formats only, and a real e-tax BCTC XML.
                   That XML is the interesting part - parse_tax_xml reads it
                   deterministically, so P06 and P07 get real figures with no
                   LLM call at all.

  case_nhieu_ky_bctc  a dossier carrying financial statements for two periods,
                   one of them in both formats at once. It exists because the
                   period used to be decided by whichever file sorted first,
                   and because the e-tax figures must win over the scanned ones
                   for the same period.

  case_thieu_ho_so a deficient dossier: mandatory items absent, a .csv and a
                   .jpg where a document belongs. It exists to prove the
                   checks can see a bad dossier, which a clean sample never
                   demonstrates.

Everything here is invented. Every generated document carries a header saying
so, because a synthetic bank record that does not announce itself is a document
somebody can mistake for a real one.

Filenames matter as much as content: the checklist in BRD 2.3.a is matched from
the file name by document_classification.filename_keyword_owner, so each name
below is written to hit exactly one document type.
"""

import shutil
import sys
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SAMPLES = ROOT / "samples"
# The one real artefact reused here: an e-tax financial statement that
# parse_tax_xml can read. Copied rather than regenerated, because a hand-written
# imitation would test the parser against our own assumptions instead of the
# format.
SOURCE_BCTC_XML = ROOT.parent / "2. SME_creditmemo" / "docs" / "BCTC_sample.xml"

SYNTHETIC_BANNER = (
    "TÀI LIỆU MẪU — DỮ LIỆU GIẢ ĐỊNH, TẠO TỰ ĐỘNG ĐỂ KIỂM THỬ. "
    "KHÔNG PHẢI CHỨNG TỪ THẬT VÀ KHÔNG CÓ GIÁ TRỊ PHÁP LÝ."
)

# Matches the taxpayer in BCTC_sample.xml so the dossier is internally coherent.
TAX_CODE = "0201123795"
CUSTOMER = "CÔNG TY CỔ PHẦN XÂY DỰNG - THƯƠNG MẠI KIM HẢI"
ADDRESS = "Số 10, P. Láng Hạ, Q. Đống Đa, TP. Hà Nội"
OWNER = "Nguyễn Văn A"
OWNER_ID = "001080001234"
OWNER_BORN = "1980"
INDUSTRY = "Xây dựng công trình dân dụng và thương mại"


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_docx(path: Path, title: str, lines: list[str]) -> None:
    """A minimal but valid .docx, built with zipfile so no library is needed.

    python-docx is what READS these (src/utils/reading/extractors.py); writing
    them by hand here keeps the sample generator runnable before dependencies
    are installed.
    """

    def paragraph(text: str) -> str:
        safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        return f'<w:p><w:r><w:t xml:space="preserve">{safe}</w:t></w:r></w:p>'

    body = "".join(paragraph(line) for line in [SYNTHETIC_BANNER, "", title, ""] + lines)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="word/document.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
        "</Relationships>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)


def write_xlsx(path: Path, title: str, rows: list[list[object]]) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]
    sheet.append([SYNTHETIC_BANNER])
    sheet.append([])
    sheet.append([title])
    sheet.append([])
    for row in rows:
        sheet.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


# A font that actually carries Vietnamese diacritics. The PIL default is a
# bitmap ASCII face and would render the accents as blanks, which would make the
# OCR test pass for the wrong reason.
SCAN_FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
SCAN_SIZE = (1654, 2339)          # A4 at 200 DPI
SCAN_DPI = 200.0


def write_signed_pdf(path: Path, title: str, lines: list[str]) -> None:
    """A text PDF carrying a signature dictionary, as a signed filing does.

    The dictionary is STRUCTURAL ONLY - a real certificate is not invented here,
    and nothing in this project verifies one. It exists so the PDF half of
    src/utils/reading/digital_signature.py is exercised by a sample dossier and
    not only by bytes crafted inside a check.
    """

    text = "\n".join([SYNTHETIC_BANNER, "", title, ""] + lines)
    content = "BT /F1 9 Tf 40 780 Td 12 TL\n" + "".join(
        f"({line.replace(chr(92), '')[:88]}) Tj T*\n" for line in text.splitlines()
    ) + "ET"
    stream = content.encode("latin-1", "replace")

    objects = [
        b"<</Type/Catalog/Pages 2 0 R/AcroForm<</SigFlags 3/Fields[6 0 R]>>>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R/Annots[6 0 R]>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        b"<</Type/Annot/Subtype/Widget/FT/Sig/T(Signature1)/Rect[0 0 0 0]/V 7 0 R>>",
        b"<</Type/Sig/Filter/Adobe.PPKLite/SubFilter/adbe.pkcs7.detached"
        b"/ByteRange[0 1000 2000 3000]/Contents<308006092a864886f70d010702>"
        b"/M(D:20260320120000+07'00')>>",
    ]

    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj".encode() + body + b"endobj\n"
    start_xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n"
            f"{start_xref}\n%%EOF\n").encode()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))


def write_scanned_pdf(path: Path, title: str, lines: list[str],
                      extra_pages: list[list[str]] | None = None) -> None:
    """A page of text rendered to an image and wrapped in a PDF - a scan.

    The point is what it does NOT contain: no font, no text layer, nothing a
    parser can read. It is the only sample that forces src/utils/reading/ocr.py
    to run, and without one the OCR path - 593 lines of it - is never exercised
    by the suite at all.

    Needs Tesseract to be read back: brew install tesseract tesseract-lang.
    """

    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(SCAN_FONT, 34)

    def render(body: list[str]) -> "Image.Image":
        image = Image.new("L", SCAN_SIZE, 255)
        draw = ImageDraw.Draw(image)
        y = 140
        for line in body:
            draw.text((120, y), line, font=font, fill=30)
            y += 58
        return image

    first = render([SYNTHETIC_BANNER, "", title, ""] + lines)
    rest = [render([SYNTHETIC_BANNER, ""] + page) for page in extra_pages or []]
    path.parent.mkdir(parents=True, exist_ok=True)
    first.save(path, "PDF", resolution=SCAN_DPI, save_all=bool(rest), append_images=rest)


def write_csv(path: Path, rows: list[list[str]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([SYNTHETIC_BANNER])
        writer.writerows(rows)


def write_photo_collage_pdf(path: Path, count: int = 4) -> None:
    """One PDF page holding `count` SEPARATE embedded photographs.

    This is the shape most real photo dossiers take: an RM pastes four or six
    shots into a Word page and exports it. Rendering such a page as one image
    would cost each photo most of its resolution and collapse four scenes into a
    single answer, so the extraction pulls the photographs out individually - and
    that branch needs a fixture whose page really does carry several image
    objects, which a flattened image cannot provide.
    """

    from PIL import Image

    def photo(colour: tuple[int, int, int], size: tuple[int, int] = (480, 360)) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", size, colour).save(buffer, "JPEG", quality=85)
        return buffer.getvalue()

    palette = [(200, 40, 40), (40, 160, 60), (40, 80, 200), (220, 180, 40)]
    pictures = [photo(palette[index % len(palette)]) for index in range(count)]
    # A company logo in the header, as these pages always have. It is an embedded
    # image too, and must NOT be read as a photograph of the business - the size
    # floor in the extraction is what keeps it out, and this is what tests it.
    sizes = [(480, 360)] * count + [(64, 64)]
    pictures.append(photo((10, 10, 10), size=(64, 64)))

    objects: dict[int, bytes] = {}
    for index, data in enumerate(pictures):
        width, height = sizes[index]
        objects[5 + index] = (
            f"<</Type/XObject/Subtype/Image/Width {width}/Height {height}".encode()
            + b"/ColorSpace/DeviceRGB/BitsPerComponent 8/Filter/DCTDecode"
            b"/Length " + str(len(data)).encode() + b">>stream\n" + data + b"\nendstream"
        )

    spots = [(50, 450), (310, 450), (50, 120), (310, 120)]
    placements = [
        f"q 240 0 0 180 {spots[i % len(spots)][0]} {spots[i % len(spots)][1]} cm "
        f"/Im{i} Do Q".encode()
        for i in range(count)
    ]
    # The logo, drawn small in the header where these pages always put it.
    placements.append(f"q 40 0 0 40 50 760 cm /Im{count} Do Q".encode())
    content = b"\n".join(placements)
    objects[4] = b"<</Length " + str(len(content)).encode() + b">>stream\n" + content + b"\nendstream"
    resources = b"/XObject<<" + b"".join(
        f"/Im{i} {5 + i} 0 R".encode() for i in range(len(pictures))) + b">>"
    objects[3] = (b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<<"
                  + resources + b">>/Contents 4 0 R>>")
    objects[2] = b"<</Type/Pages/Kids[3 0 R]/Count 1>>"
    objects[1] = b"<</Type/Catalog/Pages 2 0 R>>"

    out = bytearray(b"%PDF-1.7\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj".encode() + objects[number] + b"endobj\n"
    start_xref = len(out)
    out += f"xref\n0 {max(objects) + 1}\n0000000000 65535 f \n".encode()
    for number in sorted(objects):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += (f"trailer<</Size {max(objects) + 1}/Root 1 0 R>>\nstartxref\n"
            f"{start_xref}\n%%EOF\n").encode()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))


def write_jpeg_placeholder(path: Path, marker: bytes = b"") -> None:
    """A 1x1 JPEG.

    It carries no scene a vision model could read, and cannot: no real site-visit
    photograph belongs in this repository. What it does exercise is everything
    around the vision pass - the file is discovered, identified as the photo
    document type by its name, accepted by the format rule, and routed to the
    SITEVISIT_PHOTO pass. What the model would SEE is graded from fixtures
    instead, in verify_persona_evidence.
    """

    payload = bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300"
        "0806060706050806070707090908" + "0a" * 50 +
        "ffc0000b080001000101011100ffc40014000100000000000000000000000000000009"
        "ffda0008010100003f00d2cf20ffd9"
    )
    # A JPEG comment segment keeps two placeholders from being byte-identical:
    # the pipeline de-duplicates by file hash, so identical photos would collapse
    # into one document and the sample would silently test half of what it claims.
    if marker:
        comment = b"\xff\xfe" + (len(marker) + 2).to_bytes(2, "big") + marker
        payload = payload[:2] + comment + payload[2:]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


# ---------------------------------------------------------------------------
# case_demo - a complete B1CP dossier
# ---------------------------------------------------------------------------

def build_case_demo(root: Path) -> None:
    write_docx(
        root / "ho_so_phap_ly" / "giay_chung_nhan_dang_ky_kinh_doanh.docx",
        "GIẤY CHỨNG NHẬN ĐĂNG KÝ DOANH NGHIỆP",
        [
            f"Tên doanh nghiệp: {CUSTOMER}",
            f"Mã số doanh nghiệp: {TAX_CODE}",
            f"Địa chỉ trụ sở chính: {ADDRESS}",
            f"Người đại diện theo pháp luật: {OWNER}",
            f"Số CCCD: {OWNER_ID} — Năm sinh: {OWNER_BORN}",
            f"Ngành nghề kinh doanh chính: {INDUSTRY}",
            "Ngày cấp: 15/03/2019",
            "Đã ký và đóng dấu.",
        ],
    )

    # The e-tax XML: read deterministically by parse_tax_xml, no LLM involved.
    financial = root / "ho_so_tai_chinh" / "bao_cao_tai_chinh_2025.xml"
    financial.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_BCTC_XML, financial)

    write_xlsx(
        root / "ho_so_tai_chinh" / "bang_can_doi_ke_toan_2025.xlsx",
        "BẢNG CÂN ĐỐI KẾ TOÁN",
        [
            ["Đơn vị: đồng", "", ""],
            ["Chỉ tiêu", "Mã số", "Năm 2025", "Năm 2024"],
            ["TỔNG CỘNG TÀI SẢN", "270", 50226331878, 47704469267],
            ["TỔNG CỘNG NGUỒN VỐN", "440", 50226331878, 47704469267],
            ["Người lập biểu", "Kế toán trưởng", "Giám đốc (đã ký, đã đóng dấu)"],
        ],
    )

    write_xlsx(
        root / "ho_so_tai_chinh" / "bao_cao_ket_qua_hoat_dong_kinh_doanh_2025.xlsx",
        "BÁO CÁO KẾT QUẢ KINH DOANH",
        [
            ["Đơn vị: đồng", "", ""],
            ["Chỉ tiêu", "Mã số", "Năm 2025", "Năm 2024"],
            ["Doanh thu thuần về bán hàng và cung cấp dịch vụ", "10", 62116063780, 71176996993],
            ["Lợi nhuận sau thuế thu nhập doanh nghiệp", "60", 382284650, 190395686],
            ["Người lập biểu", "Kế toán trưởng", "Giám đốc (đã ký, đã đóng dấu)"],
        ],
    )

    write_xlsx(
        root / "ho_so_tai_chinh" / "to_khai_thue_gtgt_quy_4_2025.xlsx",
        "TỜ KHAI THUẾ GTGT",
        [
            [f"Mã số thuế: {TAX_CODE}", "", ""],
            ["Kỳ tính thuế: Quý 4 năm 2025", "", ""],
            ["Chỉ tiêu", "Mã số", "Số tiền"],
            ["Tổng doanh thu hàng hoá, dịch vụ bán ra", "34", 15200000000],
            ["Đã ký điện tử.", "", ""],
        ],
    )

    write_docx(
        root / "ho_so_vay_von" / "giay_de_nghi_cap_tin_dung.docx",
        "GIẤY ĐỀ NGHỊ CẤP TÍN DỤNG",
        [
            f"Khách hàng: {CUSTOMER} — MST {TAX_CODE}",
            "",
            "B. PHƯƠNG ÁN SỬ DỤNG VỐN VÀ HIỆU QUẢ KINH DOANH",
            "Đơn vị: triệu đồng",
            "Doanh thu: 62.116",
            "Giá vốn hàng bán: 57.430",
            "Lợi nhuận: 382",
            "",
            "C. TÀI SẢN BẢO ĐẢM",
            "Đơn vị: tỷ đồng",
            "Bất động sản — Nhà xưởng tại Hà Nội — Giá trị: 8 — Chủ sở hữu: "
            f"{CUSTOMER}",
            "Tổng giá trị tài sản bảo đảm: 8",
            "",
            "D. ĐỀ NGHỊ CẤP TÍN DỤNG",
            "Đơn vị: tỷ đồng",
            "Hạn mức cho vay ngắn hạn: 3",
            "Hạn mức thấu chi: 2",
            "Tổng hạn mức đề nghị: 5",
            "",
            "Đã ký và đóng dấu.",
        ],
    )

    # A scan, not a document: this is the one sample that exercises OCR. A site
    # visit report is the most realistic thing in a dossier to arrive scanned, and
    # it routes to the SITEVISIT pass.
    write_scanned_pdf(
        root / "ho_so_soan_thao_noi_bo" / "bao_cao_khao_sat_thuc_dia.pdf",
        "BÁO CÁO KHẢO SÁT THỰC ĐỊA",
        [
            f"Khách hàng: {CUSTOMER} — MST {TAX_CODE}",
            "Ngày khảo sát: 18/12/2025",
            "Cán bộ khảo sát: Trần Thị B — RM, Chi nhánh Hà Nội",
            f"Địa điểm: {ADDRESS}",
            "",
            f"Ngành nghề hoạt động: {INDUSTRY}",
            "Sản phẩm chính: thi công công trình dân dụng; cung cấp vật liệu xây dựng",
            "",
            "Chuỗi cung ứng:",
            "Đầu vào: Công ty Thép X — thép xây dựng — trả chậm 30 ngày",
            "Đầu ra: Ban quản lý dự án Y — thi công phần thô — thanh toán theo tiến độ",
            "",
            "Kế hoạch kinh doanh năm 2026 — Đơn vị: triệu đồng",
            "Doanh thu thuần: 70.000 | Giá vốn: 64.000 | Lợi nhuận trước thuế: 900",
            "",
            "Kết luận của cán bộ khảo sát: hoạt động thực tế phù hợp hồ sơ, "
            "đề xuất tiếp tục cấp tín dụng theo hạn mức đề nghị.",
            "",
            "Đã ký và đóng dấu.",
        ],
    )

    # Site-visit photographs: LOS says this customer needs a field visit, so the
    # checklist requires them and V10 reads what they show. Two shapes on purpose
    # - loose JPEGs, and the single multi-page PDF most dossiers actually use.
    for index in (1, 2):
        write_jpeg_placeholder(
            root / "ho_so_soan_thao_noi_bo" / f"anh_khao_sat_thuc_dia_{index}.jpg",
            marker=f"anh khao sat {index}".encode(),
        )
    write_scanned_pdf(
        root / "ho_so_soan_thao_noi_bo" / "anh_khao_sat_thuc_dia_tong_hop.pdf",
        "ANH KHAO SAT THUC DIA - TRANG 1",
        [f"Khach hang: {CUSTOMER}", "Toan canh nha xuong."],
        extra_pages=[
            ["TRANG 2", "", "Khu vuc may moc va day chuyen."],
            ["TRANG 3", "", "Kho hang va cong nhan dang lam viec."],
        ],
    )
    write_photo_collage_pdf(
        root / "ho_so_soan_thao_noi_bo" / "anh_khao_sat_thuc_dia_ghep_trang.pdf"
    )

    write_docx(
        root / "ho_so_tai_san_dam_bao" / "ho_so_tai_san_bao_dam.docx",
        "HỒ SƠ TÀI SẢN BẢO ĐẢM",
        [
            f"Chủ sở hữu: {CUSTOMER}",
            "Loại tài sản: Bất động sản — Nhà xưởng tại Hà Nội",
            "Giá trị định giá: 8.000.000.000 đồng",
            "Tình trạng: đã thế chấp, chưa giải chấp",
        ],
    )


# ---------------------------------------------------------------------------
# case_nhieu_ky_bctc - two periods, one of them in two formats
# ---------------------------------------------------------------------------

# Deliberately different from the real figures in the XML, so a test can tell
# which source a number came from. The XML must win for 2024.
SCANNED_2024_TOTAL_ASSETS = 44_000_000_000
SCANNED_2024_NET_REVENUE = 66_000_000_000


def _xml_for_year(source: Path, target: Path, year: int) -> None:
    """A copy of the e-tax filing shifted to another period.

    The figures are left alone and only the declared period moves, so the file
    stays a faithful example of the format while giving the merge logic a second
    period to work with.
    """

    text = source.read_text(encoding="utf-8")
    for old, new in (
        ("2025-01-01", f"{year}-01-01"), ("2025-12-31", f"{year}-12-31"),
        ("01/01/2025", f"01/01/{year}"), ("31/12/2025", f"31/12/{year}"),
        ("<kyKKhai>2025</kyKKhai>", f"<kyKKhai>{year}</kyKKhai>"),
    ):
        text = text.replace(old, new)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def build_case_nhieu_ky_bctc(root: Path) -> None:
    box = root / "ho_so_tai_chinh"

    # 2025: only a scanned-style workbook, which is the model path.
    write_xlsx(
        box / "bao_cao_tai_chinh_2025.xlsx",
        "BÁO CÁO TÀI CHÍNH 2025",
        [
            ["Đơn vị: đồng", "", ""],
            ["Chỉ tiêu", "Mã số", "Năm 2025"],
            ["TỔNG CỘNG TÀI SẢN", "270", 50226331878],
            ["TỔNG CỘNG NGUỒN VỐN", "440", 50226331878],
            ["Doanh thu thuần về bán hàng và cung cấp dịch vụ", "10", 62116063780],
        ],
    )

    # A signed PDF filing, so the PDF branch of the signature detector is
    # exercised by a real file. P05 reads it whether or not an LLM ever parses it.
    write_signed_pdf(
        box / "bao_cao_tai_chinh_2023_da_ky_so.pdf",
        "BÁO CÁO TÀI CHÍNH 2023 (BAN CO CHU KY SO)",
        [
            f"Ma so thue: {TAX_CODE}",
            "TONG CONG TAI SAN: 47704469267",
            "TONG CONG NGUON VON: 47704469267",
        ],
    )

    # 2024: the same period twice - once as an e-tax filing, once as a scan
    # carrying different numbers. The filing must win.
    _xml_for_year(SOURCE_BCTC_XML, box / "bao_cao_tai_chinh_2024.xml", 2024)
    write_xlsx(
        box / "bao_cao_tai_chinh_2024_ban_scan.xlsx",
        "BÁO CÁO TÀI CHÍNH 2024",
        [
            ["Đơn vị: đồng", "", ""],
            ["Chỉ tiêu", "Mã số", "Năm 2024"],
            ["TỔNG CỘNG TÀI SẢN", "270", SCANNED_2024_TOTAL_ASSETS],
            ["TỔNG CỘNG NGUỒN VỐN", "440", SCANNED_2024_TOTAL_ASSETS],
            ["Doanh thu thuần về bán hàng và cung cấp dịch vụ", "10", SCANNED_2024_NET_REVENUE],
        ],
    )


# ---------------------------------------------------------------------------
# case_thieu_ho_so - a deficient dossier
# ---------------------------------------------------------------------------

def build_case_thieu_ho_so(root: Path) -> None:
    # Present, but the customer name and tax code disagree with the other
    # documents, so the cross-document consistency rule has something to find.
    write_docx(
        root / "ho_so_phap_ly" / "giay_chung_nhan_dang_ky_kinh_doanh.docx",
        "GIẤY CHỨNG NHẬN ĐĂNG KÝ DOANH NGHIỆP",
        [
            "Tên doanh nghiệp: CÔNG TY CỔ PHẦN XÂY DỰNG KIM HẢI",
            "Mã số doanh nghiệp: 0201999999",
            f"Địa chỉ trụ sở chính: {ADDRESS}",
            "Người đại diện theo pháp luật: Trần Thị B",
            "Ngành nghề kinh doanh chính: Kinh doanh bất động sản",
            "Chưa đóng dấu.",
        ],
    )

    # A permitted-to-read but not permitted-by-regulation format, and a photo no
    # reader can open. Both must reach rule P03.
    write_csv(
        root / "ho_so_tai_chinh" / "bao_cao_tai_chinh_2025.csv",
        [
            ["Chỉ tiêu", "Năm 2025"],
            ["TỔNG CỘNG TÀI SẢN", "50226331878"],
            ["TỔNG CỘNG NGUỒN VỐN", "48000000000"],
        ],
    )
    write_jpeg_placeholder(
        root / "ho_so_vay_von" / "giay_de_nghi_cap_tin_dung_scan.jpg"
    )

    # Missing on purpose: bang_can_doi_ke_toan, bao_cao_ket_qua_kinh_doanh,
    # to_khai_thue_gtgt, bao_cao_khao_sat_thuc_dia.


# ---------------------------------------------------------------------------

def main() -> None:
    if not SOURCE_BCTC_XML.exists():
        raise SystemExit(
            f"missing {SOURCE_BCTC_XML}. The e-tax financial statement is copied "
            f"from the SME_creditmemo project rather than invented, so that the "
            f"XML parser is tested against the real format."
        )

    for name, builder in (("case_demo", build_case_demo),
                          ("case_nhieu_ky_bctc", build_case_nhieu_ky_bctc),
                          ("case_thieu_ho_so", build_case_thieu_ho_so)):
        root = SAMPLES / name
        if root.exists():
            shutil.rmtree(root)
        builder(root)
        files = sorted(path for path in root.rglob("*") if path.is_file())
        print(f"{name}: {len(files)} file(s)")
        for path in files:
            print(f"    {path.relative_to(root)}")


if __name__ == "__main__":
    main()
