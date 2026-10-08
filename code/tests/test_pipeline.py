"""pipeline.parse is the only public entry point and must not crash."""

import time

from app.errors import EMPTY_DOCUMENT, TIMEOUT, UNSUPPORTED_FORMAT
from app.pipeline import parse


def test_empty_returns_structured_error():
    result = parse(b"", "empty.bin")
    assert result["error_code"] == EMPTY_DOCUMENT
    assert "message" in result


def test_unsupported_returns_structured_error():
    result = parse(b"???? not a real file", "notes.txt")
    assert result["error_code"] == UNSUPPORTED_FORMAT


def test_pdf_detect_returns_document_stub():
    result = parse(b"%PDF-1.4\n%%EOF\n", "report.pdf")
    assert "error_code" not in result
    assert result["format"] == "pdf"
    assert result["filename"] == "report.pdf"
    assert result["pages"] == []
    assert result["doc_id"]
    assert any("Phase 1" in w for w in result["warnings"])


def test_png_detect_returns_document_stub():
    result = parse(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "scan.png")
    assert result["format"] == "png"
    assert "error_code" not in result


def test_parse_never_raises_on_none():
    result = parse(None, "x")  # type: ignore[arg-type]
    assert "error_code" in result


def test_timeout_returns_timeout_code(monkeypatch):
    def hang(_file_bytes, _filename):
        time.sleep(5)
        raise AssertionError("should have timed out")

    monkeypatch.setattr("app.pipeline._parse_inner", hang)
    monkeypatch.setattr("app.pipeline.PARSE_TIMEOUT_SECONDS", 0.2)
    result = parse(b"%PDF-1.4\n", "slow.pdf")
    assert result["error_code"] == TIMEOUT
