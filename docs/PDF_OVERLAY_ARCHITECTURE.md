# PDF overlay architecture

The viewer obtains a tenant-authorized PNG rendering of one PDF page and places an independent percentage-based overlay layer above it. Projection is `left=x0/page_width`, `top=y0/page_height`, `width=(x1-x0)/page_width`, and `height=(y1-y0)/page_height`; zoom therefore preserves alignment.

Overlay types are `FIELD`, `TABLE`, and `OCR_REGION`, with styling reserved for `ROW`, `COLUMN`, `VALIDATION_ERROR`, and `SELECTION`. Clicking evidence selects its page and real box. Legacy bank rows without provenance produce no box. This layer is reusable by Phase 4 but contains no template editing.
