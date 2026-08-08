# Public Baseline Sanitization Report

## Result

**SAFE TO PUSH PUBLICLY: YES**

This verdict covers the current Git candidates and staging state. Review the
index again immediately before any future commit or push.

## Phase 2 remediation

The account-shaped source seed was classified as a legacy initialization
fallback. Existing database values remain authoritative and untouched. Fresh
empty databases now receive `SYNTHETIC-ACCOUNT` only when no default-company
bank account exists. Regression tests protect fresh initialization and existing
database compatibility.

## Final review

- 185 current Git candidates reviewed; no DB, SQLite, PDF, spreadsheet, CSV,
  XML, private key, credential file, `.env`, or private fixture is a candidate.
- No files are staged, no remote is configured, and no push was performed.
- The local `.env` is ignored and contains password-free URLs; the password file
  is stored under the user's PostgreSQL configuration outside the repository.
- Source scans find no private key, access key, assigned non-synthetic secret,
  personal email address, or non-synthetic account-shaped value. CI credentials
  are visibly synthetic and exist only for the disposable test service.
- Shape-valid GSTIN/invoice values are confined to explicitly synthetic tests.
- The ignored local database and local JSON may retain real values; they are not
  public candidates and were not modified.

Ignore rules cover database/JSON data, uploads, exports, logs, archives, `.env`,
nested Streamlit secrets, `v2_data`, private fixtures, dependencies, and Next.js
build output.
