# V2 Backend Foundation

This FastAPI service is non-authoritative in Phase 1. The legacy Streamlit application and SQLite database remain production.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn v2.backend.app.main:app --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET /health`
- `GET /api/v2/system/info`
- OpenAPI: `/docs`

The service starts without PostgreSQL or Cloudflare credentials. It never exposes production company, mapping, document, or database values through foundation endpoints.
