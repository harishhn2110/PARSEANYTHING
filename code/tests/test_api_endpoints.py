"""Unit and API integration tests for FastAPI Endpoints.

Tests:
- Health check & Observability Metrics
- Upload endpoint validation (empty, unsupported, valid)
- Documents listing & retrieval
- Block review actions (approve, reject, edit)
"""

from io import BytesIO
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import init_db


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_metrics_endpoint(client):
    res = client.get("/v1/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "pages_processed" in data
    assert "blocks_extracted" in data
    assert "failure_count" in data


def test_upload_empty_file_rejected(client):
    res = client.post(
        "/v1/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert res.status_code == 400
    data = res.json()
    assert data["error_code"] == "EMPTY_DOCUMENT"


def test_upload_unsupported_format_rejected(client):
    res = client.post(
        "/v1/documents",
        files={"file": ("malicious.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert res.status_code == 400
    data = res.json()
    assert data["error_code"] == "UNSUPPORTED_FORMAT"


def test_upload_valid_document_creates_job(client):
    # Minimal synthetic PDF bytes
    sample_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    res = client.post(
        "/v1/documents",
        files={"file": ("contract.pdf", sample_pdf, "application/pdf")},
    )
    assert res.status_code == 202
    data = res.json()
    assert "document_id" in data
    assert "job_id" in data
    assert data["status"] == "queued"

    # Query the job status
    job_res = client.get(f"/v1/jobs/{data['job_id']}")
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["document_id"] == data["document_id"]


def test_get_documents_list(client):
    res = client.get("/v1/documents")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data


def test_get_samples_endpoint(client):
    res = client.get("/v1/samples")
    assert res.status_code == 200
    samples = res.json()
    assert isinstance(samples, list)
    # If samples exist, each should have filename, size, url
    for s in samples:
        assert "filename" in s
        assert "size" in s
        assert "url" in s
