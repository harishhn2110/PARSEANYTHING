# ParseAnything Atlas

Universal document ingestion: messy files → structured Markdown + JSON, with every block traceable to page, bounding box, block id, and confidence.

Hackathon MVP for DataQuest 3.0 (DQCL / Cenizas Labs). Built phase by phase.

## Status

| Piece | State | Implementation |
| --- | --- | --- |
| Format detection (magic bytes) | **Completed** | `app/detect.py` |
| `pipeline.parse` timeout + structured errors | **Completed** | `app/pipeline.py`, `app/errors.py` |
| FastAPI upload (`POST /v1/documents`) | **Completed** | `backend/main.py`, `backend/validation.py` |
| Document + Job records + job polling | **Completed** | `backend/models.py`, `backend/worker.py` |
| Original file storage (local disk / MinIO S3) | **Completed** | `backend/storage.py` |
| Atlas UI upload/progress wired to API | **Completed** | `atlas-ingest.js` ↔ `atlas-ui.html` |
| Digital PDF text / bboxes | **Completed** | `app/extractors/pdf_extractor.py` |
| OCR for scans & raster images | **Completed** | `app/extractors/image_extractor.py` |
| Table extraction & arithmetic reconciliation | **Completed** | `app/validation/table_reconciliation.py` |
| Office (DOCX, XLSX, PPTX) + EML extractors | **Completed** | `app/extractors/office_extractor.py` |
| Semantic Assembly & Cross-Page Table Merge | **Completed** | `app/assembly.py` |
| Trust Gate & Confidence Scoring | **Completed** | `app/trust_gate.py` |
| Grounded Document Q&A with Citations | **Completed** | `app/features/ask.py` |
| Human-in-the-Loop Review Queue | **Completed** | `backend/main.py` (`/review` endpoints) |
| Non-destructive PII Masking | **Completed** | `app/features/pii.py` |
| Multi-format Exports (MD, JSON, CSV, XLSX) | **Completed** | `app/features/export.py` |
| Dockerization & docker-compose | **Completed** | `Dockerfile`, `docker-compose.yml` |
| Multi-stage Benchmark Suite | **Completed** | `benchmark.py` |
| Full Test Suite | **Completed** | `tests/test_*.py` |

## Setup

Python 3.10+ (developed against Python 3.10+):

```bash
python -m pip install -r requirements.txt
```

### MinIO (Optional)
With `S3_ACCESS_KEY` / `S3_SECRET_KEY` unset, originals go to `data/objects/`. To run with MinIO:

```bash
docker compose up -d
```

Copy `.env.example` to `.env` and fill in the MinIO keys.

## Run the API + Web App

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Open your browser to:
- **Web App**: http://127.0.0.1:8000/ or http://127.0.0.1:8000/atlas-ui.html
- **API Docs**: http://127.0.0.1:8000/docs
- **Health Check**: http://127.0.0.1:8000/health
- **Metrics**: http://127.0.0.1:8000/v1/metrics

You can also open `code/atlas-ui.html` or the root `index.html` directly in any web browser.

## Running Tests

Run the full pytest suite:

```bash
pytest -v
```

Tests include:
- `tests/test_detect.py`: Magic byte format detection and edge cases
- `tests/test_pipeline.py`: Public entry point `parse()` and timeout enforcement
- `tests/test_extractors.py`: Office, EML, and Image OCR extractions
- `tests/test_reconciliation.py`: Table math checks (Qty × Price, column totals, YoY growth)
- `tests/test_features.py`: Grounded Q&A, PII masking, and multi-format exporters
- `tests/test_api_endpoints.py`: FastAPI endpoints, uploads, reviews, metrics

## Running Benchmarks

```bash
python benchmark.py
```

Evaluates detection throughput, arithmetic table reconciliation, grounded Q&A citation latency, and automatically discovers & parses all user PDF documents placed in `code/samples/` or the parent `samples/` directory with per-document timing, block count, and confidence scores.

## Architecture & Layout

```text
code/
├── atlas-ui.html       # Atlas UX single-page application (Document, Understand, Validate, Ask, Verify, Review, Export)
├── atlas-ingest.js     # Client ↔ API bridge (Uploads, job polling, Q&A, reviews, exports)
├── Dockerfile          # Production container setup with Tesseract & Poppler
├── docker-compose.yml  # Multi-container Compose config (app + MinIO)
├── benchmark.py        # Multi-stage performance and accuracy evaluation
│
├── backend/            # FastAPI REST API & Worker
│   ├── main.py         # App routes & endpoints
│   ├── worker.py       # Asynchronous ingestion pipeline
│   ├── models.py       # SQLAlchemy ORM schemas
│   ├── storage.py      # Local / MinIO object store abstraction
│   ├── db.py           # Database engine & session
│   └── config.py       # Pydantic settings
│
├── app/                # Document Intelligence Core
│   ├── pipeline.py     # parse() entry point with 60s timeout
│   ├── detect.py       # Magic-byte detection
│   ├── router.py       # Layout-aware parser routing
│   ├── trust_gate.py   # Confidence thresholding & status assignment
│   ├── assembly.py     # Semantic assembly & reading order
│   ├── extractors/     # PDF, Office, and Image adapters
│   ├── validation/     # Deterministic table reconciliation engine
│   └── features/       # Grounded Q&A, Exports, and PII masking
│
└── tests/              # Pytest test suite
```
