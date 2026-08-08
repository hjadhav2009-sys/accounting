# Batch persistence

`document_batches` stores tenant/company/creator, state, timestamps, total, queued, running, processed and outcome counters. Documents and metrics carry `batch_id`. Counter updates are atomic and tenant scoped. APIs return percentage, documents and category/currency accounting groups.

Execution is local and in-process. On startup, unfinished batches become `INTERRUPTED`, running resets to zero, and a resubmission note is persisted. Completed documents remain usable. Automatic replay is absent because unprocessed request bytes are not a durable queue.
