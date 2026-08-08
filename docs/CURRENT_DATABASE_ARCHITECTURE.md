# Current Database Architecture

## Location and lifecycle

The active store is `data/business_rules.db`. `shared.database.connect()` opens it directly with SQLite row objects. Effective `init_db(force=False)` creates tables, seeds defaults, normalizes existing data, deduplicates rows, creates unique indexes, and sets a process-global `_DB_READY` flag. There is no transaction/repository boundary above this module.

Phase 0B inspected the database using Python SQLite URI `mode=ro&immutable=1` with `PRAGMA query_only=ON`. The live schema matches the effective creation code. Certified counts are 3 companies, 4 bank accounts, 26 party ledgers, 144 mappings, 42 voucher rules, and 0 import-history rows. The inspection found the four named unique indexes, the companies primary-key auto-index, and no foreign keys. Hashes before and after the read-only session were identical.

## Tables and PostgreSQL equivalents

| Table | Fields | Meaning | Relationships and risk | Later PostgreSQL equivalent |
|---|---|---|---|---|
| `companies` | `name TEXT PK`, `tally_company_name`, `gstin`, `state`, `suspense_ledger`, `cgst_ledger`, `sgst_ledger`, `igst_ledger` | Company profile and exact Tally ledger names | Natural-name PK; renaming is not cascaded | `organizations`, `companies(id UUID, organization_id, name, ...)`; unique normalized name per organization |
| `bank_accounts` | `id INTEGER PK AUTOINCREMENT`, `company_name`, `account_hint`, `bank_ledger`, `notes` | Detect statement/account and choose Tally bank ledger | Logical company FK only; account hints may be sensitive | `bank_accounts(id UUID, company_id FK, encrypted_account_hint/token, ...)` |
| `party_ledgers` | `id`, `company_name`, `platform`, `party_ledger`, `party_gstin`, `state` | Marketplace supplier/party mapping | Logical company FK only; platform normalization is critical | `party_ledger_mappings(id UUID, company_id FK, platform_id, ...)` |
| `ledger_mappings` | `id`, `company_name`, `tool`, `platform`, `pattern`, `voucher_type`, `ledger`, `match_type`, `enabled`, `notes` | Bank narration and marketplace expense mappings | Ordering by longest pattern affects result; regex is stored data | `ledger_mapping_rules(id UUID, company_id FK, tool enum, match_type enum, priority, ...)` |
| `voucher_rules` | `id`, `company_name`, `platform`, `pdf_doc_type`, `tally_voucher_type`, `sign_mode` | Maps source document type to Tally voucher/sign behavior | String enums; company fallback | `voucher_rules(id UUID, company_id FK nullable for defaults, platform_id, document_type_id, ...)` |
| `import_history` | `id`, `company_name`, `tool`, `platform`, `invoice_no`, `voucher_type`, `voucher_date`, `amount REAL`, `source_file`, `created_at` | Intended export/import history | No current writer; `REAL` is unsafe for authoritative money | `document_exports(id UUID, company_id FK, amount NUMERIC(18,2), created_at timestamptz, ...)` |

## Indexes

- `companies`: implicit primary-key index on `name`.
- `ux_bank_accounts(company_name, account_hint, bank_ledger)`.
- `ux_party_ledgers(company_name, platform)`.
- `ux_ledger_mappings(company_name, tool, platform, pattern, voucher_type)`.
- `ux_voucher_rules(company_name, platform, pdf_doc_type)`.
- No declared index on `import_history` and no explicit foreign keys.

Deduplication keeps the minimum `id` for each unique-index key before creating the indexes. This can discard later conflicting rows without an audit record.

## Read and write locations

| Data | Reads | Writes |
|---|---|---|
| All table/schema/seed data | `shared/database.py` | `shared/database.py:init_db`, `seed_defaults`, normalization/deduplication |
| Company profile | `main_app.py`, all three app UIs, marketplace XML | Database Pro `save_company`, copy/delete/import |
| Bank accounts | Bank app export (`iloc[0]`), Database Pro | Database Pro editor/import/copy/delete |
| Party ledgers | Marketplace UI and XML | Database Pro and marketplace on-spot mapping |
| Ledger mappings | Bank/marketplace UIs and parsers through `map_ledger` | On-spot mapping and Database Pro import/editor |
| Voucher rules | Marketplace row creation and XML | Database Pro import/editor/copy/delete |
| Import history | Database Pro table helper/summary scope only | No current application writer found |

The JSON files `data/bank_tally_rules.json` and `data/marketplace_tally_settings.json` contain legacy configuration but no current source reference. The bank engine still contains JSON-payload helper functions, but the current UI routes mapping through SQLite.

## Lookup and normalization contracts

- `norm_text`: collapse all whitespace to one space and trim.
- `norm_platform`: remove all whitespace and lowercase.
- Company-specific mapping is checked first, then `Default Company`.
- Mapping candidates are ordered by descending pattern length.
- `contains` and `smart_contains` are equivalent substring tests in the shared DB implementation.
- `equals`, `starts_with`, and case-insensitive `regex` are supported.
- Disabled mappings are ignored.
- Party fallback: selected platform, default platform, selected `unknown`, default `unknown`, then literal `Suspense`.
- Voucher fallback: Credit Note becomes Debit Note/reverse; otherwise Purchase/charge.
- Blank pattern or blank ledger is rejected by `add_mapping`.

## Backup, repair, import, cache, and migration risks

- `backup_database()` copies into `data/` with a timestamp; `.gitignore` covers these `.db` files.
- Database Pro backs up before Excel import, but normal edits and cleanup do not automatically back up.
- `cleanup_database()` normalizes and deduplicates in place.
- Replace-mode Excel import deletes the entire selected company table before inserting accepted rows.
- Boolean conversion during Excel import uses Python truthiness, so a string such as `"False"` may become enabled; this needs a regression/fix decision later.
- `REAL` values and string dates must become `NUMERIC` and proper date/time types in PostgreSQL.
- Default-company inheritance should be explicit policy, not a magic company row.
- Migrate IDs and company ownership before adding Row-Level Security. Validate row counts, normalized keys, collisions, fallback results, and golden XML before cutover.
