# AI Template Studio tool contract

Phase 4 performs no AI inference. Future AI may read bounded selection/document/extraction/validation context and propose calls to: create/update/delete field mapping, create table, update columns, create anchor, set ignore region, run tests/validation and create a new draft version.

Every call follows: AI → authenticated Template Action API → authorization → schema validation → revision check → domain service → tenant-scoped repository → audit. AI never receives raw SQL/filesystem access, cannot mutate approved versions, approve/deprecate, bypass validation, alter accounting values or post Tally vouchers. Selection context is currently returned locally with `external_transmission=false` and `ai_enabled=false`.
