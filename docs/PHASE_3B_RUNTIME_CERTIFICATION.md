# Phase 3B runtime certification

Runtime: PostgreSQL 18.4; Tesseract 5.4.0.20240606 at `C:\Program Files\Tesseract-OCR\tesseract.exe`; languages `eng`, `osd`; local-only startup PASS.

Certified behaviors: native OCR skip, deficient-page-only invocation, real scanned mixed-GST OCR, exact numeric provenance, deterministic reconciliation, calibrated low-confidence review, unavailable/process/timeout/empty handling, native table rows/cells/box, source overlays, document/review filters, search, durable batch counters/progress/refresh, independent failure, grouped summary, unified reports, dashboard, format health and unknown-format review.

Verification: 91 discovered/passed, 0 failed/skipped; compile and dependency checks PASS; FastAPI/Next.js/Streamlit HTTP PASS; PostgreSQL five migrations healthy; production SQLite hash unchanged. No external AI/OCR/document upload. Phase 4 not started.
