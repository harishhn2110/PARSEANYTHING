"""Unit tests for Core Extractors (PDF, Office, Image).

Tests synthetic fixtures, format parsing, bounding box normalization,
and Block schema adherence.
"""

from io import BytesIO
import pytest

from app.schema import Block
from app.extractors.office_extractor import OfficeExtractor
from app.extractors.image_extractor import ImageExtractor


def test_office_extractor_corrupt_zip():
    """Corrupt office file bytes should raise CorruptFileError."""
    from app.errors import CorruptFileError

    corrupt_bytes = b"PK\x03\x04" + b"garbage_data_here"
    with pytest.raises(CorruptFileError):
        OfficeExtractor.extract_docx(corrupt_bytes, "test.docx")


def test_office_extractor_xlsx_synthetic():
    """Synthetic XLSX extraction should generate table, row, and cell blocks."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Financials"
    ws.append(["Item", "Qty", "Price", "Total"])
    ws.append(["Server A", 2, 1500, 3000])
    ws.append(["Server B", 1, 2000, 2000])

    buf = BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    blocks = OfficeExtractor.extract_xlsx(xlsx_bytes, "financials.xlsx")
    assert len(blocks) > 0
    table_block = next((b for b in blocks if b.type == "table"), None)
    assert table_block is not None
    assert "Server A" in table_block.content
    assert table_block.extractor == "openpyxl"
    assert table_block.confidence == 1.0
    assert table_block.status == "verified"


def test_office_extractor_eml_synthetic():
    """Synthetic EML parsing should extract headers and body."""
    eml_content = (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: Quarterly Revenue Report\r\n"
        b"Date: Wed, 08 Oct 2026 10:00:00 +0000\r\n"
        b"\r\n"
        b"Please find attached the quarterly figures for review.\r\n"
        b"North America revenue was $42.5M.\r\n"
    )

    blocks = OfficeExtractor.extract_eml(eml_content, "email.eml")
    assert len(blocks) >= 2
    subject_block = next((b for b in blocks if "Quarterly Revenue Report" in b.content), None)
    assert subject_block is not None
    body_block = next((b for b in blocks if "North America revenue was $42.5M" in b.content), None)
    assert body_block is not None
    assert body_block.type == "paragraph"


def test_image_extractor_synthetic():
    """Synthetic image extraction generates image/OCR block with valid bbox."""
    from PIL import Image

    # Create synthetic RGB image with text-like background
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    blocks = ImageExtractor.extract(png_bytes, "test.png")
    assert len(blocks) >= 1
    for b in blocks:
        assert isinstance(b, Block)
        assert b.page == 1
        assert len(b.bbox) == 4
        assert 0.0 <= b.confidence <= 1.0
