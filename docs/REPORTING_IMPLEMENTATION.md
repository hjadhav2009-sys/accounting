# Reporting implementation

`/api/v2/reports/unified` returns Decimal-string tenant/company/date-filtered document, invoice/GST, marketplace, bank and processing sections. Dashboard cards use real database values, provide empty states and drill into documents, reviews and format health. Processing includes success/review rates, OCR usage and durations.

`/api/v2/reports/format-health` returns family, documents seen, approved/latest versions, success/review/OCR rates, unknown variations and last seen. Invoice, marketplace and bank categories remain separate; batch totals group only compatible category/currency records.
