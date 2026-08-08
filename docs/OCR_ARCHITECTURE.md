# OCR architecture

All consumers depend on provider-neutral `OcrService`. The certified provider is local Tesseract at configurable `TESSERACT_CMD`; discovery also supports PATH and standard Windows installation. Certified runtime: `C:\Program Files\Tesseract-OCR\tesseract.exe`, version 5.4.0.20240606, languages `eng` and `osd`.

Native extraction and per-page deterministic quality scoring always run first. Only deficient pages are OCR'd sequentially. Defaults are `OCR_MAX_CONCURRENCY=1`, `OCR_TIMEOUT_SECONDS=120`, and `OCR_MAX_PAGES=50`. Results preserve raw token, safe formatting normalization, confidence, page and box. Ambiguous substitutions are flagged but never silently applied. Confidence alone never yields VERIFIED—accounting reconciliation is mandatory.

Structured failures are `OCR_UNAVAILABLE`, `OCR_FAILED`, `OCR_TIMEOUT`, and `OCR_EMPTY`. No OCR network service or external document upload exists.
