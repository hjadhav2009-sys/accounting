# Batch processing

Upload creates durable metadata and returns HTTP 202. A local FastAPI background task processes each file independently while PostgreSQL atomically persists queued/running/processed and VERIFIED/REVIEW/BLOCKED/DUPLICATE/FAILED counters. Status/document APIs restore progress after refresh; the UI polls and provides outcome drill-downs. Compatible accounting summaries are grouped by document category and currency.

One exception increments FAILED without stopping later documents. Server restart marks outstanding batches `INTERRUPTED` with explicit resubmission guidance. Metadata and completed documents survive; unprocessed in-memory payloads do not automatically replay.
