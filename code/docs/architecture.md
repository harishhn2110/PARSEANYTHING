# ParseAnything Atlas — architecture (Phase 2)

UI source of truth: `atlas-ui.html` (Document → Understand → Validate → Ask → Verify → Review → Export).
Do not replace this UI. Upload and processing status are wired to the FastAPI API.

```
Upload (UI) → POST /v1/documents → store original (MinIO/S3 or local)
                → Document + Job
                → async skeleton: detect → extracting → assembling → validating → completed
GET /v1/jobs/{id}  (progress / error_code)
GET /v1/documents  /  GET /v1/documents/{id}
```

Every extracted block must keep: `id`, `page`, `bbox`, `confidence`, `source`.
Never invent text. Flag low-confidence blocks instead.

| Module | Role |
| --- | --- |
| `app/schema.py` | Block / Page / Document fields (stable) |
| `app/errors.py` | Structured error codes |
| `app/detect.py` | Format from magic bytes, not extension |
| `app/router.py` | Format → extractor |
| `app/pipeline.py` | `parse(bytes, filename)` with 60s timeout |
| `app/extractors/` | Real extractors start in later phases |
| `backend/` | FastAPI, Document/Job store, object storage, job skeleton |
| `atlas-ui.html` | Existing Atlas UX |
| `atlas-ingest.js` | Upload + job polling bridge |
