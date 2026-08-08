# Table mapping engine

A TABLE object has a normalized region, independent type, ordered column boundaries, semantic mappings, repeating-row flag, multi-line strategy and deterministic row classifiers. Types include item, tax summary, payment, bank, summary and generic. Rows remain HEADER, ITEM, SUBTOTAL, TOTAL, TAX_SUMMARY, NOTE or IGNORE, preventing displayed totals from becoming items.

The editor moves boundaries, adds/splits or removes/merges logical columns and maps accounting semantics. Same-cell text is preserved; indent/no-numeric-neighbor continuation can join description-only continuation rows while retaining continuation sources. Tax-summary rows are never flattened to one GST rate.
