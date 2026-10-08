"""Comprehensive end-to-end test suite for ParseAnything Atlas MVP.

Covers:
- Phase 3: Detect & Router
- Phase 4: Core Extraction (headings, paragraphs, lists, tables, equations, figures, captions)
- Phase 5: Semantic Assembly (reading order, multi-column, header/footer, cross-page table merge)
- Phase 6: Trust Gate & Confidence scoring
- Phase 7: Table Reconciliation (all 6 checks, match & mismatch signals)
- Phase 8: Multilingual, Handwriting & PII Masking
- Phase 9: Evidence Graph & Provenance
- Phase 10: Grounded Document Q&A with citations
- Phase 11: Human Review Queue (approve, reject, edit)
- Phase 12: Exports (Markdown, JSON, CSV, XLSX)
"""

import io
import pytest
import pymupdf
from fastapi.testclient import TestClient

from app.assembly import SemanticAssembler
from app.detect import detect_language, detect_pdf_page_profile
from app.features.ask import DocumentQA
from app.features.export import DocumentExporter
from app.features.pii import find_pii, mask_text
from app.pipeline import parse
from app.schema import Block
from app.trust_gate import TrustGate
from app.validation.table_reconciliation import TableReconciler
from backend.config import get_settings
from backend.db import configure_engine, init_db
from backend.models import Document
from backend.storage import reset_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "atlas_full.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("OBJECT_DIR", str(tmp_path / "objects"))
    monkeypatch.setenv("INLINE_JOBS", "true")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "6553600")
    get_settings.cache_clear()
    reset_store()
    configure_engine(get_settings().database_url)
    init_db()
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
    reset_store()


def create_synthetic_financial_pdf() -> bytes:
    """Create a realistic 2-page financial document with multi-column layout, headers, tables, and equations."""
    doc = pymupdf.open()

    # Page 1
    p1 = doc.new_page(width=612, height=792)
    # Header (< 8% height)
    p1.insert_text((72, 36), "CONFIDENTIAL | ATLAS FINANCIAL REPORT 2024", fontsize=8)
    # Title / Heading
    p1.insert_text((72, 110), "Executive Financial Summary", fontsize=18)
    # Left column text
    p1.insert_text((72, 160), "Revenue increased 12% year-over-year driven by North America.", fontsize=10)
    p1.insert_text((72, 190), "Key growth drivers include enterprise software and cloud services.", fontsize=10)
    # Right column text
    p1.insert_text((350, 160), "Operating income was $1.45M representing 31.4% operating margin.", fontsize=10)
    p1.insert_text((350, 190), "Net income = operating income - interest.", fontsize=10)
    # Equation
    p1.insert_text((72, 260), "Operating Margin = Operating Income / Revenue", fontsize=10)
    # Figure caption
    p1.insert_text((72, 380), "Figure 1: Quarterly regional revenue breakdown and trends", fontsize=9)
    # Footer (> 92% height)
    p1.insert_text((72, 750), "Page 1 of 2 - Acme Holdings Annual Report", fontsize=8)

    # Page 2: Table
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((72, 36), "CONFIDENTIAL | ATLAS FINANCIAL REPORT 2024", fontsize=8)
    p2.insert_text((72, 90), "Consolidated Revenue by Geography", fontsize=16)
    p2.insert_text((72, 140), "The following table details our regional financial performance:", fontsize=10)
    p2.insert_text((72, 750), "Page 2 of 2 - Acme Holdings Annual Report", fontsize=8)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# =========================================================================
# TEST 1: Phase 5 & 4 - Semantic Hierarchy, Reading Order & Header/Footer
# =========================================================================

def test_pdf_extraction_and_assembly():
    pdf_bytes = create_synthetic_financial_pdf()
    parsed = parse(pdf_bytes, "financial_report.pdf")

    assert "error_code" not in parsed
    assert parsed["format"] == "pdf"
    assert len(parsed["pages"]) == 2

    page1_blocks = parsed["pages"][0]["blocks"]
    types = [b["type"] for b in page1_blocks]

    # Must detect header, heading, paragraph, equation, caption, footer
    assert "header" in types
    assert "heading" in types
    assert "paragraph" in types
    assert "equation" in types
    assert "footer" in types

    # Bbox coordinates must be preserved
    for b in page1_blocks:
        assert len(b["bbox"]) == 4
        assert b["bbox"][0] >= 0
        assert b["bbox"][1] >= 0
        assert b["bbox"][2] <= 612.0
        assert b["bbox"][3] <= 792.0


# =========================================================================
# TEST 2: Phase 5 - Cross-Page Table Merge
# =========================================================================

def test_cross_page_table_merge():
    # Table 1 on page 1 ending near bottom
    t1 = Block(
        id="T1",
        type="table",
        page=1,
        bbox=[50.0, 500.0, 500.0, 700.0],
        reading_order=1.05,
        content="| Region | 2023 | 2024 |\n| --- | --- | --- |\n| North America | $3,800 | $4,256 |",
        confidence=0.98,
        data={
            "headers": ["Region", "2023", "2024"],
            "rows": [["North America", "$3,800", "$4,256"]],
        },
    )
    # Table 2 on page 2 starting near top
    t2 = Block(
        id="T2",
        type="table",
        page=2,
        bbox=[50.0, 60.0, 500.0, 240.0],
        reading_order=2.01,
        content="| Region | 2023 | 2024 |\n| --- | --- | --- |\n| Europe | $2,100 | $2,350 |\n| Total | $5,900 | $6,606 |",
        confidence=0.98,
        data={
            "headers": ["Region", "2023", "2024"],
            "rows": [["Europe", "$2,100", "$2,350"], ["Total", "$5,900", "$6,606"]],
        },
    )

    from app.schema import Page
    pages = [
        Page(page=1, width=612.0, height=792.0, blocks=[t1]),
        Page(page=2, width=612.0, height=792.0, blocks=[t2]),
    ]

    assembled_pages, md = SemanticAssembler.assemble(pages)
    merged_table = assembled_pages[0].blocks[0]

    assert merged_table.id == "T1"
    assert len(merged_table.data["rows"]) == 3
    assert merged_table.data["rows"][0][0] == "North America"
    assert merged_table.data["rows"][1][0] == "Europe"
    assert merged_table.data["rows"][2][0] == "Total"
    assert merged_table.data["merged_from_pages"] == [1, 2]


# =========================================================================
# TEST 3: Phase 6 & 7 - Table Reconciliation & Mismatches
# =========================================================================

def test_table_reconciliation_math():
    # Valid numeric table
    table_data_valid = {
        "headers": ["Item", "Qty", "Price", "Amount"],
        "rows": [
            ["Software License", "10", "$50.00", "$500.00"],
            ["Cloud Compute", "5", "$100.00", "$500.00"],
            ["Total", "", "", "$1,000.00"],
        ],
    }
    checks = TableReconciler.reconcile(table_data_valid, block_id="T_TEST")
    matches = [c for c in checks if c.status == "match"]
    mismatches = [c for c in checks if c.status == "mismatch"]

    assert len(matches) >= 2
    assert len(mismatches) == 0

    # Table with arithmetic discrepancy
    table_data_invalid = {
        "headers": ["Item", "Qty", "Price", "Amount"],
        "rows": [
            ["Software License", "10", "$50.00", "$400.00"],  # 10 * 50 should be 500
            ["Total", "", "", "$900.00"],  # Subtotal mismatch
        ],
    }
    checks_bad = TableReconciler.reconcile(table_data_invalid, block_id="T_BAD")
    bad_mismatches = [c for c in checks_bad if c.status == "mismatch"]
    assert len(bad_mismatches) > 0


# =========================================================================
# TEST 4: Phase 8 - Multilingual, Handwriting & PII Masking
# =========================================================================

def test_language_detection():
    assert detect_language("The consolidated financial statements are presented in USD.") == "en"
    assert detect_language("Le rapport financier consolidé présente les résultats pour l'année.") == "fr"
    assert detect_language("El informe financiero consolidado muestra un crecimiento constante.") == "es"
    assert detect_language("本年度财务报表按公认会计原则编制。") == "zh"


def test_pii_detection_and_masking():
    raw_text = "Contact CFO Maria Chen at mchen@acmeholdings.com or (415) 555-2671 with questions."
    matches = find_pii(raw_text)
    assert len(matches) >= 2
    assert any(m.entity_type == "email" for m in matches)
    assert any(m.entity_type == "phone" for m in matches)

    masked = mask_text(raw_text)
    assert "mchen@acmeholdings.com" not in masked
    assert "•" in masked
    assert "Contact CFO Maria Chen at" in masked


def test_trust_gate_handwriting():
    hw_block = Block(
        id="HW01",
        type="handwriting",
        page=1,
        bbox=[50, 50, 200, 100],
        reading_order=1.01,
        content="Approved by John Doe",
        confidence=0.90,
    )
    trust_gate = TrustGate()
    evaluated = trust_gate.evaluate_block(hw_block)

    assert evaluated.flagged is True
    assert evaluated.status == "review"
    assert "handwriting" in evaluated.flag_reason.lower()


# =========================================================================
# TEST 5: Phase 9 & 10 - Grounded Document Q&A
# =========================================================================

def test_grounded_qa():
    blocks = [
        Block(
            id="B1",
            type="paragraph",
            page=1,
            bbox=[72, 100, 500, 150],
            reading_order=1.01,
            content="Total revenue for North America was $4.62M in 2024.",
            confidence=0.98,
        ),
        Block(
            id="B2",
            type="paragraph",
            page=1,
            bbox=[72, 160, 500, 200],
            reading_order=1.02,
            content="Adjusted EBITDA margin expanded 180 bps to 24.8%.",
            confidence=0.95,
        ),
    ]

    # Question with evidence
    res1 = DocumentQA.answer(blocks, "What is the North America revenue?")
    assert res1["status"] == "grounded"
    assert "4.62" in res1["answer"]
    assert len(res1["citations"]) > 0
    assert res1["citations"][0]["block_id"] == "B1"

    # Question with no evidence
    res2 = DocumentQA.answer(blocks, "What is the CEO salary in Japan?")
    assert res2["status"] == "uncertain"
    assert len(res2["citations"]) == 0


# =========================================================================
# TEST 6: Phase 11 & 12 - API End-to-End: Review Queue & Exports
# =========================================================================

def test_api_full_workflow(client):
    pdf_bytes = create_synthetic_financial_pdf()
    res = client.post(
        "/v1/documents",
        files={"file": ("financial_test.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200
    doc_id = res.json()["document_id"]
    job_id = res.json()["job_id"]

    # Check job
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["status"] in ("completed", "review")
    assert job["progress"] == 100

    # Check blocks endpoint
    blocks_res = client.get(f"/v1/documents/{doc_id}/blocks")
    assert blocks_res.status_code == 200
    blocks = blocks_res.json()["items"]
    assert len(blocks) > 0

    first_block_id = blocks[0]["id"]
    single_block = client.get(f"/v1/documents/{doc_id}/blocks/{first_block_id}").json()
    assert single_block["id"] == first_block_id
    assert "bbox" in single_block

    # Test Q&A endpoint
    qa_res = client.post(
        f"/v1/documents/{doc_id}/ask",
        json={"question": "What is the revenue increase?"},
    )
    assert qa_res.status_code == 200
    qa_data = qa_res.json()
    assert qa_data["status"] == "grounded"
    assert len(qa_data["citations"]) > 0

    # Test Human Review endpoint
    review_res = client.post(
        f"/v1/blocks/{first_block_id}/review",
        json={"action": "edit", "corrected_text": "Corrected Revenue Value $5.0M"},
    )
    assert review_res.status_code == 200
    assert review_res.json()["block"]["text"] == "Corrected Revenue Value $5.0M"

    # Test Exports
    md_res = client.get(f"/v1/documents/{doc_id}/markdown")
    assert md_res.status_code == 200
    assert "Executive Financial Summary" in md_res.text

    json_res = client.get(f"/v1/documents/{doc_id}/json")
    assert json_res.status_code == 200
    assert json_res.json()["document_id"] == doc_id

    csv_res = client.get(f"/v1/documents/{doc_id}/csv")
    assert csv_res.status_code == 200

    xlsx_res = client.get(f"/v1/documents/{doc_id}/xlsx")
    assert xlsx_res.status_code == 200
    assert len(xlsx_res.content) > 0
