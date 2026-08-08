# Regression Test Matrix

## Test strategy

All new fixtures are synthetic text or in-memory rows. Database tests redirect `shared.database.DB_PATH` to a temporary directory before initialization. No customer PDF, statement, production DB copy, exported XML, or exported workbook is committed.

Run from the repository root after installing Python 3.10+ and `requirements.txt`:

```powershell
python -m unittest discover -s tests -t . -v
```

## Coverage added

| Required behavior | Test location | Protection |
|---|---|---|
| Company lookup | `tests/database/test_database_rules.py` | Normalized name returns correct company |
| Party lookup and newline/case normalization | same | Known party mapping survives whitespace/case |
| No known party becomes Suspense | same + marketplace test | Default known parties resolve; XML blocks known-platform Suspense |
| Marketplace ledger lookup | database match-mode test | Company rules and deterministic matching |
| Bank narration lookup / blank mapping | database and bank tests | All shared match types; blank rejected; unmatched stays Suspense |
| Sujal detection and parsing | `tests/parsers/test_pdf_to_excel_parsers.py` | Synthetic invoice 2600000122 contract |
| Quantity extraction | same | Two items total 420 |
| Mixed GST rates | parser + unit accounting test | 3% and 18% remain separate |
| Marketplace supplier detection | `tests/marketplace/test_marketplace.py` | Amazon, Meesho entities, Valmo |
| Purchase voucher | same | Voucher type, party, references, and signs |
| Debit Note | same | Reverse sign behavior |
| Tally XML and escaping | marketplace + `tests/xml/test_xml_well_formed.py` | Balanced tags, parsing, escaping |
| Excel output columns | `tests/integration/test_excel_export.py` | Exact GST columns and both sheets |
| Template detection / unknown | parser test | Both built-ins and unknown path |

## Not yet covered by an authoritative golden fixture

- Real Sujal PDF text extraction and the historical 3-row/420-quantity PDF.
- Both Flipkart stock-transfer physical layouts.
- Historical 46 marketplace PDFs / 188 rows / 46 vouchers.
- Each Amazon, Flipkart, Myntra, Meesho, Meesho Limited, Meesho Technologies, and Valmo document layout.
- A sanitized multi-page bank PDF table, Excel statement, and CSV statement.
- Database Pro Excel append/replace/backup workflow.
- Live production DB schema/data fallback results.
- Tally import acceptance against supported Tally versions.

## Phase 0B execution result

The existing `.venv/Scripts/python.exe` was found and used directly. Final execution on Python 3.14.3 ran 21 tests in 4.018 seconds: 21 passed, 0 failed, 0 skipped, 0 errors. In-memory compilation passed for 42 production/test Python files, and required module imports passed.

The first run produced 15 passes and 5 teardown errors after successful database assertions. These were classified as a pre-existing SQLite connection-lifecycle defect rather than accounting failures. A test-only `gc.collect()` was added so Windows could remove isolated temporary DB fixtures; production behavior was not changed. Python still emitted `ResourceWarning` evidence, documented in `PHASE_0_DISCOVERED_DEFECTS.md`.

The Excel integration test now round-trips the synthetic Sujal structured result and confirms numeric taxable/quantity columns, quantity total 420, taxable total 4400, and separate 3% and 18% buckets.
