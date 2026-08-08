# Domain Model

The V2 domain has no Streamlit, FastAPI, PostgreSQL, or cloud dependency. UUIDs are public-identity compatible and money uses `Decimal`.

Current Phase 1 models include `Money`, `TaxBucket`, `InvoiceHeader`, `InvoiceLine`, `BankTransaction`, `DocumentIdentity`, `ExtractionResult`, `ValidationIssue`, `ValidationResult`, `VoucherResult`, `Job`, and `AuditEvent`. Enums define validation/job status, roles, permissions, and future processing modes.

One `ExtractionResult` and one `InvoiceLine` can contain multiple `TaxBucket` objects. No `invoice.gst_rate` singleton exists. This natively represents, for example, separate IGST 3% and IGST 18% taxable/tax totals.

Future aggregates build on these primitives: organizations, companies, users/access, documents/pages/hashes, format families/template versions, invoices/items, bank transactions, marketplace documents/lines, mapping and voucher rules, review tasks, exports, AI usage, and reporting facts.

Legacy adapter outputs retain `raw_legacy_rows` for traceability. Adoption is incremental; existing engines are not forced through these models in Phase 1.
