# PostgreSQL Parity Report

Live certification compared immutable production SQLite with the PostgreSQL
development shadow across 248 business decisions:

| Category | Compared | Match |
|---|---:|---:|
| Companies | 3 | 3 |
| Bank accounts | 4 | 4 |
| Party ledgers | 26 | 26 |
| Bank mappings | 28 | 28 |
| Marketplace mappings | 116 | 116 |
| Voucher rules | 42 | 42 |
| Normalization cases | 29 | 29 |
| **Total** | **248** | **248** |

MISMATCH, MISSING_IN_POSTGRES, EXTRA_IN_POSTGRES,
NORMALIZATION_DIFFERENCE, and SHADOW_ERROR were all zero. Observations store only
category/status metadata, not private compared values.

The importer recorded one source normalization item: legacy mapping ID 466071,
field `ledger`, contains a control-whitespace character. Existing `norm_text`
replaces that character with a normal space without changing length. SQLite and
PostgreSQL returned the same ledger, so this is expected certified legacy
normalization, not a parity defect.
