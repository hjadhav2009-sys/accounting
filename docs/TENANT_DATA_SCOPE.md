# Tenant Data Scope

| Scope | Tables |
|---|---|
| Global/system | `schema_migrations` |
| Organization | organizations, users, roles, document format families, migration runs, normalization records, parity observations |
| Company (and organization) | companies, company access, bank accounts, party/GST ledgers, ledger mappings, voucher rules, documents/hashes, invoices/tax buckets, jobs, validation, bank/marketplace data, reviews, exports, audit |
| Parent-inherited | template fields/samples, document pages, extraction rows, validation issues, invoice tax buckets |

Repositories require an organization ID and include it in every root query.
Company access requires both organization and company equality. Identical
mapping text in different organizations resolves independently.

Phase 2B verified this against PostgreSQL 18: identical `Collection Fee`/RLS
patterns in separate organizations returned only their tenant ledger, and the
same SHA-256 could be stored in another tenant while same-company duplication
was rejected.
