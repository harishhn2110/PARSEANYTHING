"""HTTP ingestion: multipart upload, validation, jobs, graceful errors."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.errors import CORRUPT_FILE, EMPTY_DOCUMENT, FILE_TOO_LARGE, UNSUPPORTED_FORMAT
from backend.config import get_settings
from backend.db import configure_engine, init_db
from backend.storage import reset_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "atlas.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("OBJECT_DIR", str(tmp_path / "objects"))
    monkeypatch.setenv("INLINE_JOBS", "true")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "65536")
    get_settings.cache_clear()
    reset_store()
    configure_engine(get_settings().database_url)
    init_db()
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
    reset_store()


def _pdf(name="report.pdf"):
    return name, b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n", "application/pdf"


def test_upload_pdf_creates_document_and_job(client):
    name, data, mime = _pdf()
    res = client.post(
        "/v1/documents",
        files={"file": (name, data, mime)},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["document_id"]
    assert body["job_id"]
    assert body["filename"] == name

    job = client.get(f"/v1/jobs/{body['job_id']}").json()
    assert job["status"] in ("completed", "review")
    assert job["progress"] == 100
    assert job["document_id"] == body["document_id"]

    doc = client.get(f"/v1/documents/{body['document_id']}").json()
    assert doc["format"] == "pdf"
    assert doc["status"] in ("completed", "review")
    assert doc["size_bytes"] == len(data)
    assert "originals/" in doc["storage_key"]


def test_list_documents(client):
    client.post("/v1/documents", files={"file": _pdf()})
    res = client.get("/v1/documents")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["filename"] == "report.pdf"


def test_unsupported_extension(client):
    res = client.post(
        "/v1/documents",
        files={"file": ("notes.txt", b"%PDF-1.4\n", "text/plain")},
    )
    assert res.status_code == 400
    assert res.json()["error_code"] == UNSUPPORTED_FORMAT


def test_mime_mismatch(client):
    res = client.post(
        "/v1/documents",
        files={"file": ("scan.png", b"%PDF-1.4\n", "application/pdf")},
    )
    assert res.status_code == 400
    assert res.json()["error_code"] == UNSUPPORTED_FORMAT


def test_empty_file(client):
    res = client.post(
        "/v1/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert res.status_code == 400
    assert res.json()["error_code"] == EMPTY_DOCUMENT


def test_too_large(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "500")
    get_settings.cache_clear()
    blob = b"%PDF-1.4\n" + b"x" * 1000
    res = client.post(
        "/v1/documents",
        files={"file": ("big.pdf", blob, "application/pdf")},
    )
    assert res.status_code == 413
    assert res.json()["error_code"] == FILE_TOO_LARGE


def test_corrupt_zip_as_docx(client):
    res = client.post(
        "/v1/documents",
        files={
            "file": (
                "broken.docx",
                b"PK\x03\x04" + b"not-a-real-zip",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error_code"] == CORRUPT_FILE


def test_jpeg_upload(client):
    data = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    res = client.post(
        "/v1/documents",
        files={"file": ("photo.jpg", data, "image/jpeg")},
    )
    assert res.status_code == 200
    doc = client.get(f"/v1/documents/{res.json()['document_id']}").json()
    assert doc["format"] == "jpg"
    assert doc["status"] in ("completed", "review")


def test_xlsx_magic_ok(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
    data = buf.getvalue()
    res = client.post(
        "/v1/documents",
        files={
            "file": (
                "sheet.xlsx",
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 200
    job = client.get(f"/v1/jobs/{res.json()['job_id']}").json()
    assert job["status"] in ("completed", "review")


def test_malformed_missing_file(client):
    res = client.post("/v1/documents")
    assert res.status_code in (400, 422)


def test_unknown_ids(client):
    assert client.get("/v1/documents/does-not-exist").status_code == 404
    assert client.get("/v1/jobs/does-not-exist").status_code == 404
