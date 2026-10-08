"""Placeholder extractor used until format-specific extractors exist."""

import uuid

from app.schema import Document


def extract(file_bytes: bytes, filename: str, fmt: str) -> Document:
    return Document(
        doc_id=str(uuid.uuid4()),
        filename=filename,
        format=fmt,
        pages=[],
        markdown="",
        warnings=[
            f"Detected {fmt.upper()}, but extraction is not implemented yet (Phase 1 skeleton)."
        ],
        errors=[],
    )
