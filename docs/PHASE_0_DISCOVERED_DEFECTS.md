# Phase 0 Discovered Defects

## SQLite connections are not explicitly closed

- **Classification:** C — actual pre-existing production defect.
- **Reproduction:** Run the database regression tests on Windows with `DB_PATH` redirected to a temporary database. All lookup/mapping assertions complete, but teardown cannot delete the temporary database because it remains open. Five database tests initially ended with `PermissionError: [WinError 32]`.
- **Affected module:** `shared/database.py`, including functions using `with connect() as conn:`.
- **Cause:** A `sqlite3.Connection` context manager commits or rolls back a transaction but does not close the connection on exit. Connections remain open until garbage collection.
- **Severity:** Low for current single-process/local operation; potentially medium for reliable backup, database replacement, long-running resource use, and future concurrent migration tooling.
- **Existed before Phase 0:** Yes. Phase 0 added tests but did not change this connection pattern.
- **Certification handling:** Production code was not changed. Test teardown explicitly calls `gc.collect()` before deleting its isolated temporary fixture.
- **Suggested future fix:** Introduce an explicitly closing connection context manager or `contextlib.closing(connect())`, then regression-test every read/write path and production DB backup/replace behavior before adoption.
# Phase 2 disposition

Re-inspected, not fixed. The warning comes from repeated legacy call sites that
use SQLite connection context managers for transaction scope; Python's SQLite
context manager does not close the connection. Correcting it safely would touch
shared lifecycle behavior across the certified legacy database layer, so it is
not a tiny isolated maintenance change. Tests continue to collect during
teardown and the warning remains documented; accounting semantics were not mixed
with this migration phase.
