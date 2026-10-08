"""Unit tests for Advanced Features: Grounded Q&A, PII Masking, and Exporters.

Covers:
- Phase 8: PII Detection & Masking
- Phase 10: Grounded Document Q&A with Bounding Box Citations
- Phase 12: Traceable Exports (Markdown, JSON, CSV, XLSX)
"""

from io import BytesIO
import json
import pytest

from app.schema import Block
from app.features.ask import DocumentQA
from app.features.pii import find_pii, mask_text
from app.features.export import DocumentExporter


def test_pii_detection():
    sample_text = (
        "Contact harish@example.com or call 555-123-4567. "
        "SSN is 123-45-6789 and Card is 4111 2222 3333 4444."
    )
    matches = find_pii(sample_text)
    types = [m.entity_type for m in matches]
    assert "email" in types
    assert "phone" in types
    assert "ssn" in types
    assert "credit_card" in types


def test_pii_masking():
    sample = "Please send payment to alice@corp.com or 555-888-9999."
    masked = mask_text(sample, mask_char="*")
    assert "alice@corp.com" not in masked
    assert "555-888-9999" not in masked
    assert "*" in masked


def test_grounded_qa_with_citations():
    blocks = [
        Block(
            id="blk_001",
            page=1,
            bbox=[50.0, 100.0, 500.0, 140.0],
            type="heading",
            content="Regional Revenue Performance 2026",
            confidence=0.98,
            extractor="pymupdf",
            extractor_version="1.0",
            reading_order=1,
        ),
        Block(
            id="blk_002",
            page=1,
            bbox=[50.0, 150.0, 500.0, 200.0],
            type="paragraph",
            content="North America revenue reached $42.5M, exceeding target by 14%.",
            confidence=0.96,
            extractor="pymupdf",
            extractor_version="1.0",
            reading_order=2,
        ),
        Block(
            id="blk_003",
            page=1,
            bbox=[50.0, 220.0, 500.0, 260.0],
            type="paragraph",
            content="EMEA revenue stood at $28.3M, reflecting steady enterprise adoption.",
            confidence=0.94,
            extractor="pymupdf",
            extractor_version="1.0",
            reading_order=3,
        ),
    ]

    # Grounded question
    res = DocumentQA.answer(blocks, "What is the North America revenue?")
    assert res["status"] in ("grounded", "estimated")
    assert "$42.5M" in res["answer"] or "North America" in res["answer"]
    assert len(res["citations"]) > 0
    cite = res["citations"][0]
    assert cite["block_id"] == "blk_002"
    assert cite["page"] == 1
    assert cite["bbox"] == [50.0, 150.0, 500.0, 200.0]

    # Non-existent information -> uncertain
    res_unknown = DocumentQA.answer(blocks, "What was the quantum teleportation throughput?")
    assert res_unknown["status"] == "uncertain"
    assert "cannot verify" in res_unknown["answer"].lower() or "not found" in res_unknown["answer"].lower() or "no mention" in res_unknown["answer"].lower() or "uncertain" in res_unknown["status"]


def test_export_markdown_and_json():
    # Mocking a Document-like object hierarchy
    class MockPage:
        def __init__(self, page_number, blocks):
            self.page_number = page_number
            self.blocks = blocks

    class MockDoc:
        def __init__(self, filename, pages):
            self.filename = filename
            self.overall_confidence = 0.95
            self.pages_rel = pages

    blocks = [
        Block(id="b1", page=1, bbox=[10, 10, 100, 20], type="heading", content="Executive Summary", confidence=1.0, reading_order=1),
        Block(id="b2", page=1, bbox=[10, 30, 200, 50], type="paragraph", content="Contact ceo@test.com for details.", confidence=0.9, reading_order=2),
    ]
    doc = MockDoc("report.pdf", [MockPage(1, blocks)])

    # Plain markdown
    md = DocumentExporter.to_markdown(doc, masked=False)
    assert "# report.pdf" in md
    assert "## Executive Summary" in md
    assert "ceo@test.com" in md

    # Masked markdown
    md_masked = DocumentExporter.to_markdown(doc, masked=True)
    assert "ceo@test.com" not in md_masked

    # JSON export
    data = DocumentExporter.to_json_dict(doc, masked=False)
    assert data["filename"] == "report.pdf"
    assert len(data["pages"]) == 1
    assert len(data["pages"][0]["blocks"]) == 2
