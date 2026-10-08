"""JSON shapes returned and accepted by the HTTP API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    error_code: str
    message: str


class UploadAccepted(BaseModel):
    document_id: str
    job_id: str
    filename: str
    status: str


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    format: str
    size_bytes: int
    pages: int = 0
    storage_key: str
    status: str
    overall_confidence: float = 0.0
    job_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentOut] = Field(default_factory=list)


class JobOut(BaseModel):
    id: str
    document_id: str
    status: str
    progress: int
    stage: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class BlockOut(BaseModel):
    id: str
    document_id: str
    page: int
    parent_id: str | None = None
    type: str
    text: str
    bbox: list[float] | None = None
    confidence: float
    status: str
    extractor: str
    extractor_version: str
    reading_order: float
    language: str
    flagged: bool
    flag_reason: str | None = None
    data: Any = None
    lineage: list[dict[str, Any]] = Field(default_factory=list)
    validation_events: list[dict[str, Any]] = Field(default_factory=list)


class BlockList(BaseModel):
    items: list[BlockOut] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    confidence: float
    status: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class ReviewActionRequest(BaseModel):
    action: str = "approve"  # approve, reject, edit
    corrected_text: str | None = None


class ValidationEventOut(BaseModel):
    id: str
    document_id: str
    block_id: str | None = None
    type: str
    message: str
    severity: str
    expected: str | None = None
    actual: str | None = None
    difference: str | None = None
    status: str
