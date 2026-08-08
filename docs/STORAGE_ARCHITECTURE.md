# Storage Architecture

`DocumentStorage` separates document bytes from database metadata. Phase 1 implements only `LocalFilesystemStorage`; future NAS and object-storage implementations use the same interface.

Storage keys are generated from organization/company/document UUIDs plus a bounded suffix. User filenames never select directories. Every resolved key is checked to remain inside the configured root. Writes return storage key, SHA-256, and byte size. Actual PDFs remain outside PostgreSQL.

Future metadata contains document/company/organization IDs, hash, original filename, MIME type, size, storage key, creator, and timestamp. Phase 1 does not move existing uploads. `v2_data/` is ignored by Git.
