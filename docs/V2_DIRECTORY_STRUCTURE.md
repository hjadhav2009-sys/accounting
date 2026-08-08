# V2 Directory Structure

```text
v2/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routes and public DTOs
│   │   ├── audit/            # append-only development audit store
│   │   ├── config/           # environment-backed settings
│   │   ├── domain/           # framework-independent accounting concepts
│   │   ├── infrastructure/   # SQLite adapters and migration verifier
│   │   ├── jobs/             # in-process development job state
│   │   ├── repositories/     # application protocols
│   │   ├── security/         # centralized role/permission evaluation
│   │   ├── services/         # legacy, storage, validation, AI boundaries
│   │   └── main.py           # non-authoritative FastAPI composition
│   ├── migrations/           # PostgreSQL design migrations; never auto-run
│   └── README.md
└── frontend/
    ├── app/                  # Next.js App Router shell
    ├── components/           # reusable operator-facing components
    ├── package.json / package-lock.json
    └── README.md
```

The existing `apps/`, `shared/`, `data/`, and `main_app.py` remain in place. V2 can be removed by deleting `v2/`, `tests/v2/`, and V2 documentation/dependency files; legacy startup paths do not import V2.
