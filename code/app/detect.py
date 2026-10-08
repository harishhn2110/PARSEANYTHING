"""Identify file format and per-page layout/content characteristics.

Format detection uses magic bytes / file headers.
Page detection identifies digital text vs scans, tables, charts, equations, handwriting, language, and layout.
"""

from dataclasses import asdict, dataclass
from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile

from app.errors import CORRUPT_FILE, EMPTY_DOCUMENT, UNSUPPORTED_FORMAT, ParseError, make_error

# Supported Formats
PDF = "pdf"
DOCX = "docx"
XLSX = "xlsx"
PPTX = "pptx"
PNG = "png"
JPG = "jpg"
EML = "eml"

SUPPORTED = (PDF, DOCX, XLSX, PPTX, PNG, JPG, EML)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK"
OLE_MAGIC = b"\xd0\xcf\x11\xe0"


@dataclass
class PageProfile:
    page_number: int
    is_digital: bool
    is_scan: bool
    has_tables: bool
    has_figures: bool
    has_equations: bool
    has_handwriting: bool
    language: str = "en"
    layout: str = "single_column"  # single_column, multi_column, tabular
    char_count: int = 0
    image_count: int = 0
    confidence_estimate: float = 0.95

    def to_dict(self) -> dict:
        return asdict(self)


def _looks_like_eml(data: bytes) -> bool:
    """EML is plain text with mail headers."""
    sample = data[:4096]
    try:
        text = sample.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            text = sample.decode("latin-1")
        except UnicodeDecodeError:
            return False
    if b"\x00" in sample:
        return False
    lines = text.replace("\r\n", "\n").split("\n")[:40]
    header_names = (
        "from:",
        "to:",
        "subject:",
        "date:",
        "mime-version:",
        "received:",
        "content-type:",
        "message-id:",
        "return-path:",
    )
    hits = 0
    for line in lines:
        lower = line.lower()
        if lower.startswith(header_names):
            hits += 1
        if line.startswith("From "):
            hits += 1
    return hits >= 2


def _office_kind_from_zip(data: bytes) -> str | ParseError:
    try:
        with ZipFile(BytesIO(data)) as zf:
            names = zf.namelist()
    except BadZipFile:
        return make_error(CORRUPT_FILE, "File looks like a zip archive but is not readable.")

    if any(n.startswith("word/") for n in names):
        return DOCX
    if any(n.startswith("xl/") for n in names):
        return XLSX
    if any(n.startswith("ppt/") for n in names):
        return PPTX
    if "[Content_Types].xml" in names:
        return make_error(UNSUPPORTED_FORMAT, "ZIP/OOXML file is not DOCX, XLSX, or PPTX.")
    return make_error(UNSUPPORTED_FORMAT, "ZIP archive is not a supported Office format.")


def detect(file_bytes: bytes) -> str | ParseError:
    """Return a format string (pdf, docx, ...) or a ParseError."""
    if file_bytes is None or len(file_bytes) == 0:
        return make_error(EMPTY_DOCUMENT, "File is empty.")

    if file_bytes.startswith(PDF_MAGIC):
        return PDF
    if file_bytes.startswith(PNG_MAGIC):
        return PNG
    if file_bytes.startswith(JPEG_MAGIC):
        return JPG
    if file_bytes.startswith(ZIP_MAGIC):
        return _office_kind_from_zip(file_bytes)
    if file_bytes.startswith(OLE_MAGIC):
        return make_error(
            UNSUPPORTED_FORMAT,
            "Legacy OLE Office files (.doc/.xls/.ppt) are not supported. Use DOCX/XLSX/PPTX.",
        )
    if _looks_like_eml(file_bytes):
        return EML

    return make_error(
        UNSUPPORTED_FORMAT,
        "Could not identify file as PDF, DOCX, XLSX, PPTX, PNG, JPG, or EML.",
    )


def detect_language(text: str) -> str:
    """Heuristic language detection for common documents."""
    if not text or len(text.strip()) < 10:
        return "en"
    # CJK
    if re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", text):
        return "zh"
    # Cyrillic
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    # Arabic
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    # Devanagari
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"
    # French markers
    if re.search(r"\b(le|la|les|des|du|dans|pour|avec|sont|est)\b", text, re.IGNORECASE):
        return "fr"
    # Spanish markers
    if re.search(r"\b(el|los|las|del|por|para|con|como|este)\b", text, re.IGNORECASE):
        return "es"
    # German markers
    if re.search(r"\b(der|die|das|und|f\u00fcr|mit|nicht|eine)\b", text, re.IGNORECASE):
        return "de"
    return "en"


def detect_pdf_page_profile(doc_or_bytes, page_number: int) -> PageProfile:
    """Analyze a PDF page to detect characteristics for routing."""
    import pymupdf

    if isinstance(doc_or_bytes, bytes):
        doc = pymupdf.open(stream=doc_or_bytes, filetype="pdf")
    else:
        doc = doc_or_bytes

    if page_number < 1 or page_number > len(doc):
        page_number = 1
    page = doc[page_number - 1]

    text = page.get_text() or ""
    char_count = len(text.strip())
    image_list = page.get_images()
    image_count = len(image_list)

    # Scanned check: few characters but has images
    is_scan = (char_count < 40 and image_count > 0)
    is_digital = not is_scan and char_count >= 10

    # Layout: detect multi-column by clustering block x-origins
    text_blocks = page.get_text("blocks") or []
    layout = "single_column"
    if len(text_blocks) >= 4:
        x_coords = [b[0] for b in text_blocks]
        width = page.rect.width
        left_half = sum(1 for x in x_coords if x < width * 0.45)
        right_half = sum(1 for x in x_coords if x > width * 0.50)
        if left_half >= 2 and right_half >= 2:
            layout = "multi_column"

    # Table detection: PyMuPDF find_tables or table grid line heuristic
    has_tables = False
    try:
        tabs = page.find_tables()
        if tabs and len(tabs.tables) > 0:
            has_tables = True
    except Exception:
        has_tables = bool(re.search(r"(\|[^\n]+\||\b(Revenue|Total|Assets|Liabilities)\b.*?\$\d+)", text))

    # Figure / Chart detection
    drawings = page.get_drawings() or []
    has_figures = image_count > 0 or len(drawings) > 10

    # Equation detection
    math_patterns = [
        r"(\b[a-zA-Z]\s*=\s*[\w\d\+\-\*\/]+)",
        r"(\b(EBITDA|margin|operating income)\s*=\s*)",
        r"[\u2211\u222B\u00D7\u00F7\u2212\u2248\u2264\u2265]",
        r"(\b\d+\s*[\+\-\*\/]\s*\d+\s*=\s*\d+)",
    ]
    has_equations = any(bool(re.search(pat, text, re.IGNORECASE)) for pat in math_patterns)

    # Handwriting detection heuristic (e.g., text mentions handwriting or signature/scan)
    has_handwriting = "handwritten" in text.lower() or "signature" in text.lower() or (is_scan and char_count < 15)

    lang = detect_language(text)
    confidence = 0.96 if is_digital else 0.72

    return PageProfile(
        page_number=page_number,
        is_digital=is_digital,
        is_scan=is_scan,
        has_tables=has_tables,
        has_figures=has_figures,
        has_equations=has_equations,
        has_handwriting=has_handwriting,
        language=lang,
        layout=layout,
        char_count=char_count,
        image_count=image_count,
        confidence_estimate=confidence,
    )
