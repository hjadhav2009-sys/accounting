# Native PDF extraction

PyMuPDF opens bytes in memory, rejects corrupt/password-protected/over-page-limit inputs, and extracts text, ordered blocks/spans, font evidence, tables when detected, and image regions. Per-page and document quality signals include characters, blank ratio, numeric density, garbling, fragmentation and coverage. Native extraction always precedes OCR.

The Phase 3B ruled-table fixture has three rows and four columns (`HSN`, quantity, GST, amount). PyMuPDF recovered all 12 cells in row order and the exact table box `(40,40)-(560,190)` on a 600x400-point page. When table detection fails, lower-level text blocks remain evidence; OCR tokens are not represented as fabricated cells.
