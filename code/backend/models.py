"""Document, Page, Block, ValidationEvent, Lineage, and Job persistence models."""

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.enums import PipelineStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(255), default="")
    format: Mapped[str] = mapped_column(String(32), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(32), default=PipelineStatus.queued.value)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    pages_rel: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Page.page_number"
    )
    blocks: Mapped[list["Block"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Block.reading_order"
    )
    validation_events: Mapped[list["ValidationEvent"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float] = mapped_column(Float, default=612.0)
    height: Mapped[float] = mapped_column(Float, default=792.0)
    page_type: Mapped[str] = mapped_column(String(32), default="digital")  # digital, scanned, hybrid
    language: Mapped[str] = mapped_column(String(16), default="en")
    image_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    document: Mapped[Document] = relationship(back_populates="pages_rel")
    blocks: Mapped[list["Block"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="Block.reading_order"
    )


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("blocks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # heading, paragraph, list, table, table_row, table_cell, figure, chart, equation, caption, header, footer, handwriting
    text: Mapped[str] = mapped_column(Text, default="")
    content_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)  # [x0, y0, x1, y1]
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="verified")  # verified, review, abstain
    extractor: Mapped[str] = mapped_column(String(64), default="native_parser")
    extractor_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    reading_order: Mapped[float] = mapped_column(Float, default=0.0)
    language: Mapped[str] = mapped_column(String(16), default="en")
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    document: Mapped[Document] = relationship(back_populates="blocks")
    page: Mapped[Page | None] = relationship(back_populates="blocks")
    parent: Mapped["Block | None"] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Block"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    validation_events: Mapped[list["ValidationEvent"]] = relationship(
        back_populates="block", cascade="all, delete-orphan"
    )
    lineage: Mapped[list["Lineage"]] = relationship(
        back_populates="block", cascade="all, delete-orphan"
    )


class ValidationEvent(Base):
    __tablename__ = "validation_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("blocks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)  # table_reconciliation, trust_gate, etc.
    message: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info, warning, error
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    difference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="match")  # match, mismatch, unable_to_check
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    document: Mapped[Document] = relationship(back_populates="validation_events")
    block: Mapped[Block | None] = relationship(back_populates="validation_events")


class Lineage(Base):
    __tablename__ = "lineages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(64), default="page_bbox")
    source_ref: Mapped[str] = mapped_column(Text, default="")
    extractor: Mapped[str] = mapped_column(String(64), default="native_parser")
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    block: Mapped[Block] = relationship(back_populates="lineage")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default=PipelineStatus.queued.value)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    document: Mapped[Document] = relationship(back_populates="jobs")
