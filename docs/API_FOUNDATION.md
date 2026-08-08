# API Foundation

The Phase 1 FastAPI service is non-authoritative and binds to port 8000 for development. It exposes only:

- `GET /health`: status, API version, adapter mode.
- `GET /api/v2/system/info`: safe foundation state (legacy authority enabled, PostgreSQL cutover and AI disabled).

Future route namespaces are reserved for organizations, companies, documents, templates, reviews, bank, marketplace, reports, and admin. No production database rows or private values are exposed.

Pydantic DTOs include company, document upload/summary, extraction, validation, bank, marketplace, template, and review summaries. Public IDs are UUIDs rather than legacy sequential IDs. DTOs reject unknown fields.

Start instructions are in `v2/backend/README.md`. Authentication and RLS are intentionally not activated in Phase 1.
