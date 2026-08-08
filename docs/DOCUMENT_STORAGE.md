# Document storage

Original PDFs use `DocumentStorage`; Phase 3 uses `LocalFilesystemStorage`. Keys are `{organization}/{company}/{document}.pdf`, resolved beneath the configured storage root with traversal rejection. PostgreSQL stores the opaque key and metadata only. APIs never return the key or filesystem path; the content endpoint performs a tenant-scoped metadata lookup before reading bytes.
