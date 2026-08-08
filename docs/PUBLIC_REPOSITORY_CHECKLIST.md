# Public Repository Safety Checklist

## Current result: NOT READY TO PUBLISH

The directory is not a Git repository, so tracked files and history cannot be checked. It contains production/local data and historical reports with business identifiers. Do not initialize and publish the entire folder without a curated staging pass.

## Before first commit or push

- [ ] Create a separate encrypted backup of `data/business_rules.db` and test restore.
- [ ] Exclude/relocate the production DB, DB journals/backups, local JSON rule stores, uploads, exports, logs, audit data, and caches.
- [ ] Replace the account-shaped default seed in `shared/database.py` with a clearly synthetic value, only after tests establish migration behavior.
- [ ] Replace historical QA/debug reports containing company names, invoice numbers, or customer-derived results with sanitized summaries.
- [ ] Decide whether `BASELINE_SHA256.txt` should remain private; it fingerprints a private DB and contains an obsolete local path.
- [ ] Add only synthetic PDFs/text/workbooks/XML expectations; never customer fixtures.
- [ ] Keep `.env.example` names empty. Never add `.env`, Cloudflare tokens, DB URLs, private keys, or Streamlit secrets.
- [ ] Review every staged path and binary: `git status --short`, `git diff --cached --stat`, and `git diff --cached`.
- [ ] Run a secret scanner over staged content and, if any prior Git history exists elsewhere, scan all history.
- [ ] Run privacy patterns for email, phone, PAN, GSTIN, bank account, customer/company names, invoice/reference numbers, and addresses; manually review hits.
- [ ] Verify `.gitignore` with `git check-ignore -v` for representative private paths.
- [ ] Confirm archives (`zip/7z/rar`), SQLite files, spreadsheets, CSV, PDFs, and XML cannot be staged accidentally.
- [ ] Add license, contribution/security policy, supported-version policy, and disclosure contact before public release.
- [ ] Run tests, compile/import checks, dependency advisory scan, and generated-artifact check in CI.

## Ignore rules audited

Phase 0 retains rules for Python/env files, all local DB/JSON data, uploads, outputs, source documents, accounting exports, and credential-like files. It adds logs, audit, exports/backups, archives, Streamlit secrets, historical reports, and the private DB fingerprint file. Ignore rules are defense in depth: if files were ever tracked in another repository, ignore rules do not remove them from history.

## Safe public fixture policy

Synthetic identities must be visibly fictional; do not merely shuffle real values. Use reserved/example domains, invalid-but-shape-testable identifiers where validators permit, generated amounts, and new invoice numbers. Record the business behavior represented and expected structured result without retaining source provenance that identifies a customer.
