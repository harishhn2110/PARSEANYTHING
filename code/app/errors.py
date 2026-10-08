"""Structured error codes. Pipeline never crashes; it returns one of these."""

from dataclasses import asdict, dataclass

# Standard Phase 13 Error Codes
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
CORRUPT_FILE = "CORRUPT_FILE"
OCR_FAILED = "OCR_FAILED"
PARSER_FAILED = "PARSER_FAILED"
TABLE_EXTRACTION_FAILED = "TABLE_EXTRACTION_FAILED"
VISION_FAILED = "VISION_FAILED"
EQUATION_FAILED = "EQUATION_FAILED"
STORAGE_FAILED = "STORAGE_FAILED"
TIMEOUT = "TIMEOUT"
INTERNAL_ERROR = "INTERNAL_ERROR"

# Additional compatibility codes
ENCRYPTED_FILE = "ENCRYPTED_FILE"
EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
PARTIAL_FAILURE = "PARTIAL_FAILURE"

KNOWN_CODES = (
    UNSUPPORTED_FORMAT,
    CORRUPT_FILE,
    OCR_FAILED,
    PARSER_FAILED,
    TABLE_EXTRACTION_FAILED,
    VISION_FAILED,
    EQUATION_FAILED,
    STORAGE_FAILED,
    TIMEOUT,
    INTERNAL_ERROR,
    ENCRYPTED_FILE,
    EMPTY_DOCUMENT,
    FILE_TOO_LARGE,
    PARTIAL_FAILURE,
)


@dataclass
class ParseError(Exception):
    error_code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"

    def to_dict(self) -> dict:
        return asdict(self)


def make_error(code: str, message: str) -> ParseError:
    if code not in KNOWN_CODES:
        code = INTERNAL_ERROR
    return ParseError(error_code=code, message=message)
