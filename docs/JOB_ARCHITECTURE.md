# Job Architecture

The Phase 1 in-process manager models extraction, OCR, AI analysis, template generation, Excel/XML export, and bank reconciliation without adding a broker. Jobs carry UUID, organization/company, type, creator, status, progress, timestamps, and bounded error code.

States are QUEUED, RUNNING, REVIEW, COMPLETED, FAILED, and CANCELLED. Explicit transitions prevent terminal jobs from restarting. Raw exceptions, secrets, or document contents must not be placed in `error_code`. Later durable workers will preserve the same state machine, idempotency key, tenant context, retry policy, and audit events.
