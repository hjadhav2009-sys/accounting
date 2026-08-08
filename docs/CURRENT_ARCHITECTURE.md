# Current Architecture

## Audit scope and baseline

This document describes the preserved local Streamlit baseline as found on 2026-08-07. Phase 0 did not replace Streamlit, migrate SQLite, add AI, or rewrite parsers. By the end of Phase 0B the directory was a Git worktree on `main` with no commits, no staged files, and all source files untracked; Codex did not initialize or publish it. `data/business_rules.db` exists, is 86,016 bytes, and its SHA-256 is the value already recorded in `BASELINE_SHA256.txt`.

Phase 0B found the hidden project interpreter at `.venv/Scripts/python.exe` and completed runtime certification. PATH-level `python`/`py` remain unavailable, so commands must use the virtual-environment interpreter directly. Statements from older `*_REPORT.txt` files remain historical claims; the new synthetic test results are separately certified.

## Runtime flow

```text
main_app.py (Streamlit, localhost:8501)
├── apps/database_manager/app.py ── shared/database.py ── data/business_rules.db
├── apps/pdf_to_excel_core/app_embedded.py
│   ├── extractor/pdf_reader.py (PyMuPDF)
│   ├── extractor/parsers.py + layout_engine.py
│   ├── rules/gst_rules.py
│   └── rules/excel_rules.py (pandas/openpyxl)
├── apps/bank_to_tally_xml/app.py
│   ├── engine.py (pdfplumber/pandas, mapping and XML)
│   └── shared/database.py
└── apps/marketplace_pdf_to_tally/app.py
    ├── engine.py (PyMuPDF/pandas, mapping and XML)
    ├── smart_audit.py
    └── shared/database.py
```

`main_app.py` embeds the PDF Core by changing the process working directory, adding the app directory to `sys.path`, then executing `app_embedded.py` with `exec`. This is a fragile but behaviorally important compatibility boundary.

## Module responsibilities

| Module | Current responsibility | Important dependency/state |
|---|---|---|
| `main_app.py` | Navigation and same-port composition | Streamlit; dynamic `exec` for PDF Core |
| `shared/paths.py` | Root/data/output/upload/log directory constants | Creates directories at import time |
| `shared/database.py` | SQLite initialization, seeds, normalization, lookup, CRUD, copy, cleanup, backup | Production DB path; module `_DB_READY` cache |
| `shared/json_store.py` | Generic JSON load/save | Creates missing JSON during load; not referenced by current apps |
| `apps/database_manager/app.py` | Company/rule administration and Excel import/export | Calls all mutating DB operations |
| PDF `pdf_reader.py` | Page text extraction | PyMuPDF (`fitz`) |
| PDF `layout_engine.py` | Text cleanup, regex helpers, money/rate conversion | Deterministic |
| PDF `parsers.py` | Detection and two built-in parser families | Relative top-level imports require path workaround |
| PDF `gst_rules.py` | Group rows by invoice/rate/HSN and sum taxable/quantity | Forces configured HSN for 18% |
| PDF `excel_rules.py` | Stable GST column order and two-sheet XLSX | pandas/openpyxl |
| PDF `table_reader.py` | Optional pdfplumber table extraction | Defined but not called |
| PDF `ocr_reader.py` | OCR placeholder returning empty text | Defined but not called |
| Bank `engine.py` | PDF/Excel/CSV ingestion, grouping suggestions, legacy JSON mapping helper, voucher XML | pdfplumber/pandas |
| Bank `app.py` | Upload, DB-backed mapping, edit, export | First saved bank account selected; temporary files not deleted |
| Marketplace `engine.py` | Platform/document detection, supplier parsers, DB mapping, XML | PyMuPDF/pandas |
| Marketplace `smart_audit.py` | Row-count estimate, total hint, review checks | Informational PDF totals |
| Marketplace `app.py` | Upload, mapping, validation, audit, export | Temporary audit directory not deleted |

## Full repository tree

Generated/cache files are shown as categories to keep the inventory readable.

```text
.
├── .env.example
├── .gitignore
├── BASELINE_SHA256.txt
├── CODEX_START_HERE.md
├── CURRENT_BASELINE_STATUS.md
├── HYBRID_AI_V2_NOTES.md
├── README_START_HERE.txt and historical *_REPORT.txt / *_NOTES.txt files
├── *.bat launch, repair, and stop scripts
├── requirements.txt
├── main_app.py
├── data/
│   ├── business_rules.db                 [private production data]
│   ├── bank_tally_rules.json             [legacy/private local data]
│   ├── marketplace_tally_settings.json   [legacy/private local data]
│   └── KEEP_*.txt
├── shared/
│   ├── __init__.py
│   ├── database.py
│   ├── json_store.py
│   └── paths.py
├── uploads/.gitkeep
├── apps/
│   ├── bank_to_tally_xml/{__init__.py,app.py,engine.py}
│   ├── database_manager/{__init__.py,app.py}
│   ├── marketplace_pdf_to_tally/{__init__.py,app.py,engine.py,smart_audit.py}
│   └── pdf_to_excel_core/
│       ├── .streamlit/config.toml
│       ├── app.py, app_embedded.py, README.md, requirements.txt, *.bat
│       ├── extractor/{__init__.py,layout_engine.py,ocr_reader.py,parsers.py,pdf_reader.py,table_reader.py}
│       ├── rules/{__init__.py,excel_rules.py,gst_rules.py}
│       ├── templates/{custom_template_example.json,flipkart_stock_transfer.json,sujal_tax_invoice.json}
│       ├── database/                      [empty]
│       └── output/                        [runtime-generated]
├── tests/
│   ├── unit/
│   ├── parsers/
│   ├── database/
│   ├── marketplace/
│   ├── bank/
│   ├── xml/
│   └── integration/
└── docs/                                  [Phase 0 documents]
```

`__pycache__` directories and `.pyc` files exist throughout the baseline but are ignored and are not source of truth.

## XML architecture

Bank XML emits one Receipt or Payment per imported transaction. Deposit creates a positive counter-ledger amount and equal negative bank amount; withdrawal reverses those signs. Optional ledger-master creation is off by default. Marketplace XML groups rows by source/platform/document/voucher/invoice/date, emits one party entry, grouped expense entries, and separate CGST/SGST/IGST entries. Credit notes reverse the purchase signs. Known marketplaces are skipped entirely if their party resolves to Suspense. XML values pass through `xml.sax.saxutils.escape`.

## Excel architecture

PDF Core writes `GST Data` using a fixed ten-column contract and `Item Details` using parser detail fields. Database Pro writes one sheet per current table plus a summary sheet and imports selected sheets in append/upsert or destructive replace mode. Import creates a DB backup first. Golden tests should compare sheet names, columns, and structured values, not workbook bytes.

## Existing template architecture

Template JSON is descriptive metadata only; the parser behavior is hard-coded in `parsers.py`. The Rule Builder edits JSON files but adding JSON does not add an executable parser or detection rule. There is no version, fingerprint, confidence, schema enforcement, multi-sample test, or historical immutability.

## Files that must not be casually rewritten

- `data/business_rules.db`: current production rules and mappings.
- `shared/database.py`: effective schema, seeds, normalization, fallback semantics, and cleanup.
- `apps/pdf_to_excel_core/extractor/parsers.py` and `rules/gst_rules.py`: established quantity/GST behavior.
- `apps/marketplace_pdf_to_tally/engine.py`: supplier-specific parsing, signs, references, and party blocking.
- `apps/bank_to_tally_xml/engine.py`: statement shape and debit/credit signs.
- `apps/pdf_to_excel_core/rules/excel_rules.py`: downstream Excel contract.
- The template JSON files and default seed mappings: identifiers are user-visible contracts.

## Current risks and unanswered questions

1. `shared/database.py` duplicates most public functions; only definitions after line 418 are effective. This is dead/duplicated code but unsafe to remove without broader golden coverage.
2. Initialization is mutating: it seeds, normalizes, deduplicates, and creates indexes. Merely calling many reads can change production data on first use.
3. No foreign keys enforce company ownership; child rows can be orphaned.
4. The DB cache tracks only a process-global Boolean and cannot detect an externally replaced database.
5. Parser fallback dates may use today's date, which can silently create incorrect accounting dates.
6. Marketplace `Import?` remains true for ledger-review rows; the UI's safer `export_review=False` is the primary guard.
7. Bank export has no reconciliation or duplicate check and uses the first bank account rather than the detected account.
8. Temporary uploaded files/directories are not cleaned up.
9. Text-native PDFs only are reliably supported; OCR is a stub.
10. Whether the live DB schema differs from the code-created schema is unanswered because no SQLite/Python runtime is available for fresh introspection.
11. Private source PDFs behind historical 188-row and Sujal reports were not present, so those exact golden claims could not be independently reproduced.
12. Required Tally version/configuration, rounding policy, acceptable tolerance per document family, fiscal-year behavior, and duplicate override authority are not encoded.
