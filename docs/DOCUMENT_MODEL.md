# Document model

`DocumentRecord` owns tenant IDs, original/safe filenames, MIME, size, SHA-256, opaque storage key, pages, state, classification, accounting identity, extraction method/quality, error code, creator, and timestamps. `DocumentPage` contains point dimensions, text, blocks, spans, tables, and image regions. Detected fields and validation findings carry source references. PostgreSQL migration `003_phase3_documents.sql` persists the model without blobs.
