# Reporting Data Model

Reporting will read validated operational facts rather than recompute accounting from raw/AI output.

- Document facts: upload/process/verified/review/blocked/duplicate/new-format status, template and validator versions, durations.
- Invoice facts: supplier, invoice/document type, taxable, separate CGST/SGST/IGST and per-rate tax buckets, total.
- Marketplace facts: platform, supplier, fee type, taxable/tax, voucher type, mapping status.
- Bank facts: bank/account token, opening/credits/debits/closing, mapped/unmapped/duplicate counts, reconciliation status.
- User facts: jobs, reviews, corrections, failures, processing time and approvals.

Every fact is organization/company scoped and linked to document/job/validation/audit identifiers. API summary DTOs already avoid exposing persistence rows. Detailed dashboard endpoints and materialized views are deferred.
