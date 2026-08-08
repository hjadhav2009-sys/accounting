# V2 Backend Document Intelligence

This FastAPI service stores Phase 3 V2 document metadata in PostgreSQL. The legacy Streamlit application and SQLite database remain production-authoritative.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn v2.backend.app.main:app --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET /health`
- `GET /api/v2/system/info`
- `POST /api/v2/documents/upload` (also accepts `POST /api/v2/documents`)
- `POST /api/v2/documents/batch`
- `GET /api/v2/documents` and document detail/evidence routes
- `GET /api/v2/reviews`
- `GET /api/v2/reports/document-intelligence`
- OpenAPI: `/docs`

Document endpoints require `X-Organization-ID`, `X-Company-ID`, and `X-User-ID`. They return 503 until a V2 PostgreSQL URL is configured. No Cloudflare or remote document inference is used.
