"""Single entry point: parse(file_bytes, filename).

Wraps detect -> route -> extract in a timeout and never crashes.
Returns a full Document dict with validation events, or {error_code, message}.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from app.detect import detect
from app.errors import (
    EMPTY_DOCUMENT,
    INTERNAL_ERROR,
    PARTIAL_FAILURE,
    TIMEOUT,
    ParseError,
    make_error,
)
from app.router import route
from app.schema import Document

PARSE_TIMEOUT_SECONDS = 60


def _parse_inner(file_bytes: bytes, filename: str) -> tuple[Document, list[dict]] | ParseError:
    if file_bytes is None or len(file_bytes) == 0:
        return make_error(EMPTY_DOCUMENT, "File is empty.")

    detected = detect(file_bytes)
    if isinstance(detected, ParseError):
        return detected

    extractor = route(detected)
    if extractor is None:
        return make_error(
            PARTIAL_FAILURE,
            f"No extractor is registered for format '{detected}'.",
        )

    try:
        result = extractor(file_bytes, filename or "untitled", detected)
        if isinstance(result, tuple):
            return result
        elif isinstance(result, Document):
            return result, []
        elif isinstance(result, ParseError):
            return result
        return make_error(INTERNAL_ERROR, "Extractor returned an unexpected result.")
    except Exception as exc:
        return make_error(
            INTERNAL_ERROR,
            f"Extraction failed: {type(exc).__name__}: {exc}",
        )


def parse(file_bytes: bytes, filename: str = "untitled") -> dict:
    """Parse a file. Always returns a dict. Never raises for expected failures."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_parse_inner, file_bytes, filename)
            result = future.result(timeout=PARSE_TIMEOUT_SECONDS)
    except FuturesTimeout:
        return make_error(
            TIMEOUT,
            f"Parsing exceeded {PARSE_TIMEOUT_SECONDS} seconds.",
        ).to_dict()
    except Exception as exc:
        return make_error(
            INTERNAL_ERROR,
            f"Unexpected failure: {type(exc).__name__}: {exc}",
        ).to_dict()

    if isinstance(result, ParseError):
        return result.to_dict()

    doc, events = result
    doc_dict = doc.to_dict()
    doc_dict["validation_events"] = events
    return doc_dict
