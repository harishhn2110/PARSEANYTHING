"""Shared status values for documents, jobs, and blocks."""

from enum import StrEnum


class PipelineStatus(StrEnum):
    queued = "queued"
    detecting = "detecting"
    extracting = "extracting"
    assembling = "assembling"
    validating = "validating"
    completed = "completed"
    review = "review"
    failed = "failed"


class Severity(StrEnum):
    info = "info"
    warning = "warning"
    error = "error"


class SourceType(StrEnum):
    page_bbox = "page_bbox"
    object_store = "object_store"
    extractor = "extractor"
