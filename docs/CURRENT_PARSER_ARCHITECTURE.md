# Current Parser Architecture

## Format matrix

| Document family | Supplier/platform | Detection | Parser | Template metadata | Required signals | Output | Tests |
|---|---|---|---|---|---|---|---|
| Tax invoice | Sujal | `tax invoice` + `invoice no` + `taxable amount` | `parse_sujal_tax_invoice` | `sujal_tax_invoice.json` | Cell-per-line item table; serial, HSN, qty, unit, price, GST cell, total | Aggregated GST rows + item details | Synthetic quantity 420, 3%/18% buckets |
| Stock transfer invoice/note | Flipkart | `stock transfer` plus invoice/reference/DC marker | `parse_flipkart_stock_transfer` | `flipkart_stock_transfer.json` | Cell-per-line item fields or SKU/HSN block | Aggregated GST rows + item details | Detection covered; real-layout golden fixture missing |
| Fee invoice/credit note | Amazon | Content/name heuristics | `parse_amazon` | None | HSN/SAC-led summary rows and INR/Rs tax lines | Marketplace ledger rows | Platform/type/XML covered; real PDF golden missing |
| Fee invoice/credit note | Flipkart | Content/name heuristics | `parse_flipkart` | None | HSN then description/taxable/tax cells | Marketplace ledger rows | Platform/XML covered; real PDF golden missing |
| Fee invoice | Myntra | Content/name heuristics | `parse_myntra` | None | HSN, description, six money cells | Marketplace ledger rows | Platform/XML covered; real PDF golden missing |
| Fee invoice | Meesho generic | Content/name heuristics | `parse_meesho` | None | Serial, description, HSN, five values | Marketplace ledger rows | Platform/XML covered; real PDF golden missing |
| Supplier invoice | Meesho Limited/Fashnear | Supplier name or FTPL filename | `parse_meesho` | None | Same generic serial/HSN structure | Marketplace ledger rows | Detection covered |
| Supplier invoice | Meesho Technologies | Supplier name or MTPL filename | `parse_meesho` | None | Same generic serial/HSN structure | Marketplace ledger rows | Detection covered |
| Supplier invoice | Valmo | Supplier name or VTPL filename | `parse_meesho` | None | Same generic serial/HSN structure | Marketplace ledger rows | Detection covered |
| Bank statement PDF | Current IDBI-like 8-column layout | File extension only | `parse_pdf_tables` | None | Table row with numeric serial and at least 7 cells | Transaction DataFrame | XML/mapping covered; real table fixture missing |
| Bank statement workbook | Generic Excel/CSV | File extension only | pandas read | None | Existing expected columns | Transaction DataFrame | Not fixture-covered |
| Unknown PDF | Any | No match | no parser / review row | User may create note-only JSON | N/A | PDF Core: no rows; Marketplace: blocked review row | Unknown behavior covered |

## PDF to Excel behavior

PyMuPDF extracts plain page text. Detection and parsing are regex/line based; optional pdfplumber table extraction is not called and OCR returns an empty string. Sujal taxable is recomputed as quantity × unit price when both are truthy; otherwise it uses line total minus GST. Rows are grouped by invoice identity, rate, HSN, platform, and operator GSTIN. Mixed rates therefore remain separate. Configured `force_18_hsn` replaces every 18% HSN in aggregated output while item detail retains the parsed HSN.

Sujal falls back to a tax-summary parser if no item rows parse. With multiple tax buckets that fallback assigns quantity zero because it cannot allocate quantity reliably. Flipkart has a primary cell-per-line parser and an alternate SKU/HSN block parser.

## Marketplace behavior

Supplier-specific Meesho/Valmo checks precede generic Meesho and other marketplace checks. Document type detection prioritizes Credit Note, then Debit Note, otherwise defaults to Tax Invoice. Missing invoice/date fall back to filename and today's date respectively. Each parsed description maps through the shared database. A total mismatch greater than 1.00 or unmatched ledger produces REVIEW status.

Current validation is heuristic: row arithmetic and row-count estimates. It does not validate invoice-level displayed totals, GST rate arithmetic, HSN, date plausibility, duplicate identity, or document signatures.

## Assumptions and weaknesses

- Extraction order must match the PDFs used to develop each parser.
- Currency symbol text appears mojibake-encoded in source (`â‚¹`); behavior with correctly decoded `₹` needs a real fixture test.
- GSTIN regex requires uppercase and exact shape.
- `amount()` takes absolute value in marketplace parsing, so source signs are inferred from document type rather than retained.
- Defaulting unknown documents to Tax Invoice and missing dates to today can create plausible but wrong metadata.
- Templates are not executable or versioned and can be edited in place.
- No private PDFs were copied into tests. Synthetic text preserves structural behavior without customer information.

## Calling and export paths

PDF Core: upload → temporary file → PyMuPDF → detect → hard-coded parser → aggregate → editable DataFrame → `final_excel.xlsx`.

Marketplace: upload → private temporary directory → PyMuPDF → detect supplier/type → supplier parser → DB mapping → Smart Audit/edit → group → Tally XML.

Bank: upload → pdfplumber or pandas → narration suggestions → DB mapping/edit → per-row balanced voucher XML.
