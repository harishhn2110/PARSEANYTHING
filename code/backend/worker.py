"""Real ingestion pipeline worker.

Executes:
Detection -> Extraction -> Semantic Assembly -> Table Validation -> Trust Gate -> Evidence Lineage -> Persistence.
Renders high-res page images for the Evidence Canvas and Verify views.
"""

from datetime import datetime, timezone
import time
from typing import Any

import pymupdf
from sqlalchemy.orm import Session

from app.detect import detect
from app.errors import ParseError
from app.extractors.core import extract_document
from backend import db as db_module
from backend.enums import PipelineStatus
from backend.models import Block, Document, Job, Lineage, Page, ValidationEvent
from backend.storage import get_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fail(db: Session, document: Document, job: Job, err: ParseError) -> None:
    job.status = PipelineStatus.failed.value
    job.stage = "failed"
    job.progress = 100
    job.error_code = err.error_code
    job.error_message = err.message
    job.updated_at = _now()
    document.status = PipelineStatus.failed.value
    document.error_code = err.error_code
    document.error_message = err.message
    document.updated_at = _now()
    db.commit()


def _advance(db: Session, document: Document, job: Job, status: PipelineStatus, progress: int, stage: str) -> None:
    job.status = status.value
    job.progress = progress
    job.stage = stage
    job.updated_at = _now()
    document.status = status.value
    document.updated_at = _now()
    db.commit()


def run_ingestion_job(job_id: str) -> None:
    """Execute complete ingestion pipeline for a document."""
    db = db_module.SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        document = db.get(Document, job.document_id)
        if document is None:
            return

        # 1. Detection Stage
        _advance(db, document, job, PipelineStatus.detecting, 15, "detecting")
        store = get_store()

        try:
            payload = store.get(document.storage_key)
        except Exception as exc:
            _fail(
                db,
                document,
                job,
                ParseError(
                    error_code="STORAGE_FAILED",
                    message=f"Could not read stored original: {type(exc).__name__}: {exc}",
                ),
            )
            return

        detected = detect(payload)
        if isinstance(detected, ParseError):
            _fail(db, document, job, detected)
            return

        document.format = detected
        db.commit()

        # 2. Extracting Stage
        _advance(db, document, job, PipelineStatus.extracting, 40, "extracting")

        try:
            doc_result, validation_events = extract_document(payload, document.filename, detected)
        except Exception as exc:
            _fail(
                db,
                document,
                job,
                ParseError(
                    error_code="PARSER_FAILED",
                    message=f"Extraction failure: {type(exc).__name__}: {exc}",
                ),
            )
            return

        # 3. Assembling & Validating Stages
        _advance(db, document, job, PipelineStatus.assembling, 65, "assembling")
        _advance(db, document, job, PipelineStatus.validating, 85, "validating")

        # Render page previews for Evidence Canvas if PDF
        page_images: dict[int, str] = {}
        if detected == "pdf":
            try:
                pdf_doc = pymupdf.open(stream=payload, filetype="pdf")
                for p_idx in range(len(pdf_doc)):
                    p_num = p_idx + 1
                    pix = pdf_doc[p_idx].get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    img_key = f"pages/{document.id}/page_{p_num}.png"
                    store.put(img_key, img_bytes, "image/png")
                    page_images[p_num] = img_key
                pdf_doc.close()
            except Exception:
                pass
        elif detected in ("png", "jpg", "jpeg"):
            img_key = f"pages/{document.id}/page_1.png"
            store.put(img_key, payload, "image/png" if detected == "png" else "image/jpeg")
            page_images[1] = img_key

        # 4. Persistence to Database
        # Clean up any existing pages/blocks for idempotency
        db.query(ValidationEvent).filter(ValidationEvent.document_id == document.id).delete()
        db.query(Lineage).filter(Lineage.document_id == document.id).delete()
        db.query(Block).filter(Block.document_id == document.id).delete()
        db.query(Page).filter(Page.document_id == document.id).delete()
        db.flush()

        document.pages = len(doc_result.pages)
        document.overall_confidence = doc_result.overall_confidence
        document.metrics_json = doc_result.metrics

        # Persist Pages and Blocks
        db_page_map: dict[int, Page] = {}
        for p in doc_result.pages:
            db_page = Page(
                document_id=document.id,
                page_number=p.page,
                width=p.width,
                height=p.height,
                page_type=p.page_type,
                language=p.language,
                image_storage_key=page_images.get(p.page),
            )
            db.add(db_page)
            db.flush()
            db_page_map[p.page] = db_page

        for p in doc_result.pages:
            db_page = db_page_map[p.page]
            for b in p.blocks:
                db_block = Block(
                    id=b.id,
                    document_id=document.id,
                    page_id=db_page.id,
                    page_number=b.page,
                    parent_id=b.parent_id,
                    type=b.type,
                    text=b.content,
                    content_json=b.data,
                    bbox=b.bbox,
                    confidence=b.confidence,
                    status=b.status,
                    extractor=b.extractor,
                    extractor_version=b.extractor_version,
                    reading_order=b.reading_order,
                    language=b.language,
                    flagged=b.flagged,
                    flag_reason=b.flag_reason,
                    raw_content=b.raw_content,
                )
                db.add(db_block)

                # Persist Lineage
                lineage_item = Lineage(
                    document_id=document.id,
                    block_id=b.id,
                    source_type="page_bbox",
                    source_ref=f"page={b.page},bbox={b.bbox}",
                    extractor=b.extractor,
                    version=b.extractor_version,
                )
                db.add(lineage_item)

        # Persist Validation Events
        for ev in validation_events:
            val_ev = ValidationEvent(
                document_id=document.id,
                block_id=ev.get("block_id"),
                type=ev.get("name", "table_reconciliation"),
                message=f"{ev.get('name')}: expected {ev.get('expected')}, actual {ev.get('actual')}",
                severity=ev.get("severity", "info"),
                expected=str(ev.get("expected", "")),
                actual=str(ev.get("actual", "")),
                difference=str(ev.get("difference", "")),
                status=ev.get("status", "match"),
            )
            db.add(val_ev)

        # Check for review requirement
        has_flagged_blocks = any(b.flagged for p in doc_result.pages for b in p.blocks)
        final_status = PipelineStatus.review.value if has_flagged_blocks else PipelineStatus.completed.value

        job.status = final_status
        job.stage = "completed"
        job.progress = 100
        job.updated_at = _now()

        document.status = final_status
        document.updated_at = _now()
        db.commit()

    except Exception as exc:
        db.rollback()
        job = db.get(Job, job_id)
        document = db.get(Document, job.document_id) if job else None
        if job and document:
            _fail(
                db,
                document,
                job,
                ParseError(
                    error_code="INTERNAL_ERROR",
                    message=f"Pipeline error: {type(exc).__name__}: {exc}",
                ),
            )
    finally:
        db.close()
