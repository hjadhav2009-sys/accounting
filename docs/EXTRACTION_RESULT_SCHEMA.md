# Extraction result schema

`NormalizedExtractionResult` contains document ID, method, pages, type, supplier, invoice identity, currency, items, unlimited tax buckets, totals, bank transactions, detected fields, warnings, quality, fingerprint, family ID, and template version ID. Monetary values serialize as decimal strings. Every detected field may carry page, method, original token, confidence, normalization note, and a source box.
