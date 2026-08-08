# Repository and Adapter Architecture

Application protocols define company, ledger, mapping, bank, voucher-rule, document, template, job, and audit access without exposing database rows through APIs.

`LegacySQLiteRepositories` is a compatibility facade over `shared.database`. It delegates company normalization, company/default precedence, party fallback, mapping ordering/match types, and voucher rules to the certified implementation. It does not create new SQL or modify the production schema. SQLite remains authoritative.

Legacy service adapters call existing engines:

- `LegacyPdfToExcelService`
- `LegacyMarketplaceService`
- `LegacyBankStatementService`
- `LegacyTallyXmlService`
- `LegacyExcelExportService`

Adapters contain orchestration/import compatibility only. They do not copy GST, parser, mapping, XML-sign, or workbook logic. PostgreSQL implementations will later sit behind the same protocols and run in shadow comparison before any cutover.
