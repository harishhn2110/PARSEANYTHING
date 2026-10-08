"""MIME + extension checks for uploads. Magic-byte detection runs in the job."""

from pathlib import Path

from app.errors import FILE_TOO_LARGE, UNSUPPORTED_FORMAT, ParseError, make_error

ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".pptx": "pptx",
}

ALLOWED_MIME = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
}

# Browsers often send a generic type for Office files.
GENERIC_MIME = {"", "application/octet-stream", "binary/octet-stream"}


def extension_format(filename: str) -> str | ParseError:
    suffix = Path(filename or "").suffix.lower()
    fmt = ALLOWED_EXTENSIONS.get(suffix)
    if not fmt:
        return make_error(
            UNSUPPORTED_FORMAT,
            f"Extension '{suffix or '(none)'}' is not supported. "
            "Use PDF, PNG, JPG/JPEG, DOCX, XLSX, or PPTX.",
        )
    return fmt


def validate_upload(
    filename: str,
    content_type: str | None,
    size_bytes: int,
    max_bytes: int,
) -> str | ParseError:
    if size_bytes > max_bytes:
        return make_error(
            FILE_TOO_LARGE,
            f"File is {size_bytes} bytes; maximum allowed is {max_bytes} bytes.",
        )
    fmt = extension_format(filename)
    if isinstance(fmt, ParseError):
        return fmt
    mime = (content_type or "").split(";")[0].strip().lower()
    allowed = ALLOWED_MIME[fmt]
    if mime not in GENERIC_MIME and mime not in allowed:
        return make_error(
            UNSUPPORTED_FORMAT,
            f"MIME type '{mime}' does not match extension for {fmt.upper()}.",
        )
    return fmt
