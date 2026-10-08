"""Format detection uses file headers, not the filename extension."""

import io
import zipfile

from app.detect import DOCX, EML, JPG, PDF, PNG, PPTX, XLSX, detect
from app.errors import CORRUPT_FILE, EMPTY_DOCUMENT, UNSUPPORTED_FORMAT, ParseError


def _zip_with(names_and_bytes: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in names_and_bytes.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_empty_file():
    result = detect(b"")
    assert isinstance(result, ParseError)
    assert result.error_code == EMPTY_DOCUMENT


def test_pdf_magic_ignores_extension():
    assert detect(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n") == PDF


def test_png_magic():
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    assert detect(data) == PNG


def test_jpeg_magic():
    assert detect(b"\xff\xd8\xff\xe0" + b"\x00" * 8) == JPG


def test_docx_from_zip_parts():
    data = _zip_with(
        {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"<w:document/>",
        }
    )
    assert detect(data) == DOCX


def test_xlsx_from_zip_parts():
    data = _zip_with({"xl/workbook.xml": b"<workbook/>"})
    assert detect(data) == XLSX


def test_pptx_from_zip_parts():
    data = _zip_with({"ppt/slides/slide1.xml": b"<sld/>"})
    assert detect(data) == PPTX


def test_eml_from_headers():
    raw = (
        b"From: analyst@example.com\r\n"
        b"To: legal@example.com\r\n"
        b"Subject: Q3 pack\r\n"
        b"\r\n"
        b"Please review the attached tables.\r\n"
    )
    assert detect(raw) == EML


def test_extension_does_not_override_magic():
    # Named .pdf in real life, but bytes are JPEG.
    assert detect(b"\xff\xd8\xff\xdb" + b"\x00" * 4) == JPG


def test_random_bytes_unsupported():
    result = detect(b"this is not a document \x00\x01\x02")
    assert isinstance(result, ParseError)
    assert result.error_code == UNSUPPORTED_FORMAT


def test_corrupt_zip():
    result = detect(b"PK\x03\x04" + b"not-a-real-zip")
    assert isinstance(result, ParseError)
    assert result.error_code == CORRUPT_FILE


def test_legacy_ole_unsupported():
    result = detect(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 8)
    assert isinstance(result, ParseError)
    assert result.error_code == UNSUPPORTED_FORMAT
