SMART AUDIT

Smart Audit is a local safety checker.

It checks:
- Parsed row count vs expected PDF service rows
- Parser REVIEW rows
- Suspense/unmapped ledgers
- Zero amount rows
- Row total mismatch

It does NOT block only because PDF total hints differ, because marketplace PDFs can show:
- subtotal
- total
- negative credit note total
- net/gross different signs

So PDF total differences are INFO only, not false REVIEW.

Safe export:
- If Smart Audit says SAFE TO EXPORT, continue.
- If REVIEW appears, check those rows before exporting XML.
