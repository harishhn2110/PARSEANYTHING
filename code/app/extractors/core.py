"""Unified extraction controller for ParseAnything Atlas."""

import time
import uuid

from app.assembly import SemanticAssembler
from app.detect import DOCX, EML, JPG, PDF, PNG, PPTX, XLSX
from app.extractors.image_extractor import ImageExtractor
from app.extractors.office_extractor import OfficeExtractor
from app.extractors.pdf_extractor import PDFExtractor
from app.schema import Document, Page
from app.trust_gate import TrustGate
from app.validation.table_reconciliation import TableReconciler


def extract_document(file_bytes: bytes, filename: str, fmt: str) -> tuple[Document, list[dict]]:
    """Extract, assemble, validate, and trust-gate a document.
    
    Returns (Document, list_of_validation_events).
    """
    start_time = time.time()
    fmt_lower = (fmt or "").lower()

    if fmt_lower == PDF:
        pages = PDFExtractor.extract(file_bytes, filename)
    elif fmt_lower == DOCX:
        pages = OfficeExtractor.extract_docx(file_bytes, filename)
    elif fmt_lower == XLSX:
        pages = OfficeExtractor.extract_xlsx(file_bytes, filename)
    elif fmt_lower == PPTX:
        pages = OfficeExtractor.extract_pptx(file_bytes, filename)
    elif fmt_lower in (PNG, JPG, "jpeg"):
        pages = ImageExtractor.extract_image(file_bytes, filename)
    elif fmt_lower == EML:
        pages = OfficeExtractor.extract_eml(file_bytes, filename)
    else:
        pages = []

    # Semantic assembly: reading order, heading hierarchy, captions, table merge, markdown
    pages, full_markdown = SemanticAssembler.assemble(pages)

    # Deterministic Table Reconciliation
    all_validation_events: list[dict] = []
    trust_gate = TrustGate()

    total_confidence = 0.0
    evaluated_blocks_count = 0

    for page in pages:
        for block in page.blocks:
            signals = []
            if block.type == "table" and block.data:
                checks = TableReconciler.reconcile(block.data, block_id=block.id)
                for chk in checks:
                    evt_dict = chk.to_dict()
                    evt_dict["page"] = page.page
                    all_validation_events.append(evt_dict)
                    signals.append(evt_dict)

            # Trust Gate confidence evaluation
            trust_gate.evaluate_block(block, validation_signals=signals)
            total_confidence += block.confidence
            evaluated_blocks_count += 1

    overall_confidence = (
        round(total_confidence / evaluated_blocks_count, 2)
        if evaluated_blocks_count > 0
        else 0.95
    )

    elapsed_seconds = round(time.time() - start_time, 3)

    metrics = {
        "pages_processed": len(pages),
        "blocks_extracted": evaluated_blocks_count,
        "processing_time_seconds": elapsed_seconds,
        "validation_events_count": len(all_validation_events),
        "overall_confidence": overall_confidence,
    }

    warnings = []
    if not pages:
        warnings.append(f"Detected {fmt_lower.upper()}, but extraction is not implemented yet (Phase 1 skeleton).")

    doc = Document(
        doc_id=str(uuid.uuid4()),
        filename=filename,
        format=fmt_lower,
        pages=pages,
        markdown=full_markdown,
        warnings=warnings,
        errors=[],
        overall_confidence=overall_confidence,
        metrics=metrics,
    )

    return doc, all_validation_events
