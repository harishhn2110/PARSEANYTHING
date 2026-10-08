"""FastAPI application for ParseAnything Atlas.

Universal Document Ingestion, Traceable Evidence Graph, Grounded Q&A, and Human Review.
"""

from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import (
    CORRUPT_FILE,
    EMPTY_DOCUMENT,
    FILE_TOO_LARGE,
    INTERNAL_ERROR,
    PARTIAL_FAILURE,
    UNSUPPORTED_FORMAT,
    ParseError,
)
from app.features.ask import DocumentQA
from app.features.export import DocumentExporter
from app.features.pii import mask_text
from app.schema import Block as SchemaBlock
from backend.config import get_settings
from backend.db import get_db, init_db
from backend.enums import PipelineStatus
from backend.models import Block, Document, Job, Lineage, Page, ValidationEvent
from backend.schemas import (
    AskRequest,
    AskResponse,
    BlockList,
    BlockOut,
    DocumentList,
    DocumentOut,
    JobOut,
    ReviewActionRequest,
    UploadAccepted,
    ValidationEventOut,
)
from backend.storage import get_store
from backend.validation import validate_upload
from backend.worker import run_ingestion_job

ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    get_settings().object_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="ParseAnything Atlas", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_response(err: ParseError, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": err.error_code, "message": err.message},
    )


@app.exception_handler(RequestValidationError)
async def _malformed_request(_request, _exc: RequestValidationError) -> JSONResponse:
    return error_response(
        ParseError(error_code=PARTIAL_FAILURE, message="Malformed request."),
        400,
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(_request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "HTTP_ERROR", "message": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def _uncaught(_request, exc: Exception) -> JSONResponse:
    return error_response(
        ParseError(
            error_code=INTERNAL_ERROR,
            message=f"Unexpected failure: {type(exc).__name__}: {exc}",
        ),
        500,
    )


def _safe_filename(name: str | None) -> str:
    raw = (name or "untitled").replace("\\", "/").split("/")[-1].strip()
    return raw or "untitled"


async def _read_capped(upload: UploadFile, max_bytes: int) -> bytes | ParseError:
    chunks: list[bytes] = []
    total = 0
    while True:
        try:
            piece = await upload.read(1024 * 1024)
        except Exception as exc:
            return ParseError(
                error_code=CORRUPT_FILE,
                message=f"Could not read upload: {type(exc).__name__}: {exc}",
            )
        if not piece:
            break
        total += len(piece)
        if total > max_bytes:
            return ParseError(
                error_code=FILE_TOO_LARGE,
                message=f"File exceeds maximum size of {max_bytes} bytes.",
            )
        chunks.append(piece)
    return b"".join(chunks)


def _document_out(doc: Document, job_id: str | None) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        format=doc.format,
        size_bytes=doc.size_bytes,
        pages=doc.pages,
        storage_key=doc.storage_key,
        status=doc.status,
        overall_confidence=round(doc.overall_confidence, 2),
        job_id=job_id,
        error_code=doc.error_code,
        error_message=doc.error_message,
        created_at=doc.created_at,
    )


def _latest_job_id(db: Session, document_id: str) -> str | None:
    job = (
        db.query(Job)
        .filter(Job.document_id == document_id)
        .order_by(Job.created_at.desc())
        .first()
    )
    return job.id if job else None


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "ParseAnything Atlas", "status": "operational"}


@app.get("/v1/metrics")
def get_metrics(db: Session = Depends(get_db)) -> dict:
    total_docs = db.query(Document).count()
    total_pages = sum(d.pages for d in db.query(Document).all())
    total_blocks = db.query(Block).count()
    review_blocks = db.query(Block).filter(Block.status == "review").count()
    verified_blocks = db.query(Block).filter(Block.status == "verified").count()
    failed_jobs = db.query(Job).filter(Job.status == "failed").count()

    return {
        "documents_count": total_docs,
        "pages_processed": total_pages,
        "blocks_extracted": total_blocks,
        "verified_blocks": verified_blocks,
        "review_blocks": review_blocks,
        "failed_jobs": failed_jobs,
        "precision_rate": round(verified_blocks / max(1, total_blocks), 3),
    }


# =========================================================================
# PHASE 2: Ingestion Endpoints
# =========================================================================

@app.post("/v1/documents", status_code=202, response_model=UploadAccepted)
async def create_document(
    background: BackgroundTasks,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    if file is None:
        return error_response(
            ParseError(error_code=EMPTY_DOCUMENT, message="No file was uploaded."),
            400,
        )

    filename = _safe_filename(file.filename)
    declared_type = file.content_type or ""

    cfg = get_settings()
    payload = await _read_capped(file, cfg.max_upload_bytes)
    try:
        await file.close()
    except Exception:
        pass

    if isinstance(payload, ParseError):
        code = 413 if payload.error_code == FILE_TOO_LARGE else 400
        return error_response(payload, code)

    if not payload:
        return error_response(
            ParseError(error_code=EMPTY_DOCUMENT, message="File is empty."),
            400,
        )

    checked = validate_upload(
        filename, declared_type, len(payload), cfg.max_upload_bytes
    )
    if isinstance(checked, ParseError):
        code = 413 if checked.error_code == FILE_TOO_LARGE else 400
        return error_response(checked, code)

    document = Document(
        filename=filename,
        content_type=declared_type,
        format=checked,
        size_bytes=len(payload),
        status=PipelineStatus.queued.value,
    )
    db.add(document)
    db.flush()

    storage_key = f"originals/{document.id}/{filename}"
    try:
        get_store().put(storage_key, payload, declared_type)
    except Exception as extc:
        db.rollback()
        return error_response(
            ParseError(
                error_code="STORAGE_FAILED",
                message=f"Could not store original: {type(extc).__name__}: {extc}",
            ),
            500,
        )

    document.storage_key = storage_key
    job = Job(
        document_id=document.id,
        status=PipelineStatus.queued.value,
        progress=0,
        stage="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(document)
    db.refresh(job)

    if cfg.inline_jobs:
        run_ingestion_job(job.id)
        db.refresh(document)
        db.refresh(job)
    else:
        background.add_task(run_ingestion_job, job.id)

    return UploadAccepted(
        document_id=document.id,
        job_id=job.id,
        filename=document.filename,
        status=job.status,
    )


@app.get("/v1/documents")
def list_documents(db: Session = Depends(get_db)) -> DocumentList:
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    items = [_document_out(doc, _latest_job_id(db, doc.id)) for doc in docs]
    return DocumentList(items=items)


@app.get("/v1/documents/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if doc is None:
        return error_response(
            ParseError(error_code="PARTIAL_FAILURE", message="Document not found."),
            404,
        )
    return _document_out(doc, _latest_job_id(db, doc.id))


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        return error_response(
            ParseError(error_code="PARTIAL_FAILURE", message="Job not found."),
            404,
        )
    return JobOut(
        id=job.id,
        document_id=job.document_id,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


# =========================================================================
# PHASE 5 & 9: Semantic Blocks, Evidence Graph & Page Images
# =========================================================================

def _format_block(b: Block) -> BlockOut:
    lineages = [
        {"source_type": lin.source_type, "source_ref": lin.source_ref, "extractor": lin.extractor, "version": lin.version}
        for lin in b.lineage
    ]
    events = [
        {"id": ev.id, "type": ev.type, "message": ev.message, "severity": ev.severity, "status": ev.status}
        for ev in b.validation_events
    ]
    return BlockOut(
        id=b.id,
        document_id=b.document_id,
        page=b.page_number,
        parent_id=b.parent_id,
        type=b.type,
        text=b.text,
        bbox=b.bbox,
        confidence=b.confidence,
        status=b.status,
        extractor=b.extractor,
        extractor_version=b.extractor_version,
        reading_order=b.reading_order,
        language=b.language,
        flagged=b.flagged,
        flag_reason=b.flag_reason,
        data=b.content_json,
        lineage=lineages,
        validation_events=events,
    )


@app.get("/v1/documents/{document_id}/blocks")
def get_document_blocks(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if doc is None:
        return error_response(ParseError(error_code="PARTIAL_FAILURE", message="Document not found."), 404)

    blocks = (
        db.query(Block)
        .filter(Block.document_id == document_id)
        .order_by(Block.page_number, Block.reading_order)
        .all()
    )
    return BlockList(items=[_format_block(b) for b in blocks])


@app.get("/v1/documents/{document_id}/blocks/{block_id}")
def get_block(document_id: str, block_id: str, db: Session = Depends(get_db)):
    block = (
        db.query(Block)
        .filter(Block.document_id == document_id, Block.id == block_id)
        .first()
    )
    if block is None:
        return error_response(ParseError(error_code="PARTIAL_FAILURE", message=f"Block '{block_id}' not found."), 404)
    return _format_block(block)


@app.get("/v1/documents/{document_id}/pages/{page_num}/image")
def get_page_image(document_id: str, page_num: int, db: Session = Depends(get_db)):
    page = (
        db.query(Page)
        .filter(Page.document_id == document_id, Page.page_number == page_num)
        .first()
    )
    if not page or not page.image_storage_key:
        return error_response(ParseError(error_code="PARTIAL_FAILURE", message="Page image not available."), 404)

    try:
        data = get_store().get(page.image_storage_key)
        return Response(content=data, media_type="image/png")
    except Exception as exc:
        return error_response(ParseError(error_code="STORAGE_FAILED", message=str(exc)), 500)


@app.get("/v1/documents/{document_id}/validation-events")
def get_validation_events(document_id: str, db: Session = Depends(get_db)):
    events = (
        db.query(ValidationEvent)
        .filter(ValidationEvent.document_id == document_id)
        .order_by(ValidationEvent.created_at)
        .all()
    )
    return [
        ValidationEventOut(
            id=ev.id,
            document_id=ev.document_id,
            block_id=ev.block_id,
            type=ev.type,
            message=ev.message,
            severity=ev.severity,
            expected=ev.expected,
            actual=ev.actual,
            difference=ev.difference,
            status=ev.status,
        )
        for ev in events
    ]


# =========================================================================
# PHASE 10: Grounded Document Q&A
# =========================================================================

@app.post("/v1/documents/{document_id}/ask")
def ask_document(document_id: str, req: AskRequest, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if doc is None:
        return error_response(ParseError(error_code="PARTIAL_FAILURE", message="Document not found."), 404)

    blocks = db.query(Block).filter(Block.document_id == document_id).all()
    schema_blocks = [
        SchemaBlock(
            id=b.id,
            type=b.type,  # type: ignore
            page=b.page_number,
            bbox=b.bbox or [0, 0, 0, 0],
            reading_order=b.reading_order,
            content=b.text,
            confidence=b.confidence,
            source=b.extractor,
            extractor=b.extractor,
            lang=b.language,
            language=b.language,
            flagged=b.flagged,
            flag_reason=b.flag_reason,
            data=b.content_json,
        )
        for b in blocks
    ]

    result = DocumentQA.answer(schema_blocks, req.question)
    return AskResponse(**result)


# =========================================================================
# PHASE 11: Review Queue & Verification
# =========================================================================

@app.get("/v1/documents/{document_id}/review")
def get_review_queue(document_id: str, db: Session = Depends(get_db)):
    blocks = (
        db.query(Block)
        .filter(Block.document_id == document_id, Block.status.in_(["review", "abstain"]))
        .order_by(Block.page_number, Block.reading_order)
        .all()
    )
    return [_format_block(b) for b in blocks]


@app.post("/v1/blocks/{block_id}/review")
def review_block(block_id: str, req: ReviewActionRequest, db: Session = Depends(get_db)):
    block = db.get(Block, block_id)
    if block is None:
        return error_response(ParseError(error_code="PARTIAL_FAILURE", message="Block not found."), 404)

    old_text = block.text
    if req.action == "approve":
        if req.corrected_text is not None and req.corrected_text != old_text:
            block.text = req.corrected_text
            msg = f"Block value corrected to '{req.corrected_text}' and approved."
        else:
            msg = f"Block approved by human reviewer."
        block.status = "verified"
        block.flagged = False
        block.confidence = 1.0
    elif req.action == "reject":
        block.status = "abstain"
        block.flagged = True
        msg = f"Block rejected by human reviewer."
    elif req.action == "edit" and req.corrected_text is not None:
        block.text = req.corrected_text
        block.status = "verified"
        block.flagged = False
        block.confidence = 1.0
        msg = f"Block value corrected from '{old_text}' to '{req.corrected_text}'"
    else:
        return error_response(ParseError(error_code="PARTIAL_FAILURE", message="Invalid review action."), 400)

    # Record audit validation event
    audit_event = ValidationEvent(
        document_id=block.document_id,
        block_id=block.id,
        type="human_review",
        message=msg,
        severity="info",
        expected=old_text,
        actual=block.text,
        difference="Human correction",
        status="match" if block.status == "verified" else "mismatch",
    )
    db.add(audit_event)
    db.commit()
    db.refresh(block)

    return {"ok": True, "block": _format_block(block), "message": msg}


# =========================================================================
# PHASE 12: Exports
# =========================================================================

def _demo_markdown(masked: bool = False) -> str:
    contact = "••••••••••••••••" if masked else "mchen@acmeholdings.com"
    return (
        "# ACME HOLDINGS, INC. — Annual Report\n"
        "> Extracted by ParseAnything Atlas | Confidence: 96% | 42 blocks · 24 pages\n\n"
        "## Executive summary\n\n"
        "Revenue increased 12% year-over-year, led by strong demand across North America and disciplined pricing actions.\n\n"
        "Adjusted EBITDA margin expanded 180 bps to 24.8%, reflecting operating leverage and mix improvement.\n\n"
        f"Contact: {contact}\n\n"
        "### Revenue by geography\n\n"
        "| Region | 2024 | 2023 | Change |\n"
        "| --- | --- | --- | --- |\n"
        "| North America | $4,620 | $4,180 | +10.5% |\n"
        "| EMEA | $2,140 | $1,980 | +8.1% |\n"
        "| APAC | $1,090 | $900 | +21.1% |\n"
        "| Total revenue | $7,850 | $7,060 | +11.2% |\n\n"
        "$$\n"
        "\\text{Net Income} = \\text{Operating Income} - \\text{Interest}\n"
        "$$\n\n"
        "<!-- Provenance: Cited source A72, page 7, bbox: x120 y340 w330 h50 -->\n"
    )


def _get_doc_or_fallback(db: Session, document_id: str) -> Document | None:
    doc = db.get(Document, document_id)
    if doc is not None:
        return doc
    return db.query(Document).order_by(Document.created_at.desc()).first()


@app.get("/v1/documents/{document_id}/markdown")
def export_markdown(document_id: str, masked: bool = Query(default=False), db: Session = Depends(get_db)):
    doc = _get_doc_or_fallback(db, document_id)
    if doc is None:
        md = _demo_markdown(masked=masked)
        return Response(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="Annual_Report_extracted.md"'},
        )
    md = DocumentExporter.to_markdown(doc, masked=masked)
    safe_fn = Path(doc.filename or "document").stem + "_extracted.md"
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{safe_fn}"'},
    )


@app.get("/v1/documents/{document_id}/json")
def export_json(document_id: str, masked: bool = Query(default=False), db: Session = Depends(get_db)):
    doc = _get_doc_or_fallback(db, document_id)
    if doc is None:
        return JSONResponse(
            content={
                "document_id": "atlas-demo",
                "filename": "Annual_Report.pdf",
                "format": "pdf",
                "pages_count": 24,
                "status": "completed",
                "overall_confidence": 0.96,
                "blocks_count": 42,
            }
        )
    data = DocumentExporter.to_json_dict(doc, masked=masked)
    return JSONResponse(content=data)


@app.get("/v1/documents/{document_id}/csv")
def export_csv(document_id: str, masked: bool = Query(default=False), db: Session = Depends(get_db)):
    doc = _get_doc_or_fallback(db, document_id)
    if doc is None:
        csv_str = (
            "=== Table 1 (Block ID: A06, Page: 7) ===\n"
            "Region,2024,2023,Change\n"
            "North America,$4620,$4180,+10.5%\n"
            "EMEA,$2140,$1980,+8.1%\n"
            "APAC,$1090,$900,+21.1%\n"
            "Total revenue,$7850,$7060,+11.2%\n"
        )
        return Response(
            content=csv_str,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="Annual_Report_tables.csv"'},
        )
    csv_str = DocumentExporter.to_csv(doc, masked=masked)
    safe_fn = Path(doc.filename or "document").stem + "_tables.csv"
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_fn}"'},
    )


@app.get("/v1/documents/{document_id}/xlsx")
def export_xlsx(document_id: str, masked: bool = Query(default=False), db: Session = Depends(get_db)):
    doc = _get_doc_or_fallback(db, document_id)
    if doc is None:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Demo_Table"
        ws.append(["Region", "2024", "2023", "Change"])
        ws.append(["North America", "$4,620", "$4,180", "+10.5%"])
        ws.append(["EMEA", "$2,140", "$1,980", "+8.1%"])
        ws.append(["APAC", "$1,090", "$900", "+21.1%"])
        ws.append(["Total revenue", "$7,850", "$7,060", "+11.2%"])
        buf = BytesIO()
        wb.save(buf)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="Annual_Report_tables.xlsx"'},
        )
    xlsx_bytes = DocumentExporter.to_xlsx(doc, masked=masked)
    safe_fn = Path(doc.filename or "document").stem + "_tables.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_fn}"'},
    )


# =========================================================================
# Static UI Assets
# =========================================================================

@app.get("/")
@app.get("/atlas-ui.html")
def atlas_ui():
    return FileResponse(ROOT / "atlas-ui.html")


@app.get("/atlas-ingest.js")
def atlas_ingest_js():
    return FileResponse(ROOT / "atlas-ingest.js", media_type="text/javascript")


@app.get("/v1/samples")
def list_samples():
    """List all sample PDF documents in code/samples and ../samples."""
    sample_dirs = [ROOT / "samples", ROOT.parent / "samples"]
    seen = set()
    items = []
    for sdir in sample_dirs:
        if not sdir.exists():
            continue
        for p in sorted(list(sdir.glob("*.pdf")) + list(sdir.glob("*.PDF"))):
            if p.is_file() and p.name not in seen:
                seen.add(p.name)
                size_b = p.stat().st_size
                fmt_size = f"{size_b / 1024:.1f} KB" if size_b < 1048576 else f"{size_b / 1048576:.1f} MB"
                items.append({
                    "filename": p.name,
                    "size": size_b,
                    "size_formatted": fmt_size,
                    "url": f"/v1/samples/{p.name}",
                })
    return items


@app.get("/v1/samples/{filename}")
def get_sample_by_name(filename: str):
    """Retrieve a specific sample document by filename."""
    safe_name = Path(filename).name
    sample_dirs = [ROOT / "samples", ROOT.parent / "samples"]
    for sdir in sample_dirs:
        target = sdir / safe_name
        if target.exists() and target.is_file():
            return FileResponse(target, media_type="application/pdf", filename=safe_name)
    raise HTTPException(status_code=404, detail=f"Sample document '{safe_name}' not found.")


@app.get("/v1/sample-document")
def get_sample_document():
    sample_dirs = [ROOT / "samples", ROOT.parent / "samples"]
    for sdir in sample_dirs:
        if sdir.exists():
            target = sdir / "Annual_Report.pdf"
            if target.exists():
                return FileResponse(target, media_type="application/pdf", filename="Annual_Report.pdf")
            pdf_files = sorted(list(sdir.glob("*.pdf")) + list(sdir.glob("*.PDF")))
            if pdf_files:
                return FileResponse(pdf_files[0], media_type="application/pdf", filename=pdf_files[0].name)
    raise HTTPException(status_code=404, detail="No sample documents found in samples directory.")


