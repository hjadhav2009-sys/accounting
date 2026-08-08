# Template Studio Specification

## Goal

A professional document workspace for reviewing automatically generated draft templates. Unknown formats open with proposed regions, fields, tables, confidence, and validation impact—never a blank form. Approved history is immutable.

## Workspace

- **Left rail:** sample set, page thumbnails, format-family membership, processing state.
- **Center canvas:** high-resolution PDF, zoom/pan/page navigation, text and rectangular selection, overlays, row/column guides, ignore regions.
- **Right inspector:** extraction schema, semantic field, type/normalization, anchors, repeated-row rules, confidence, source trace, and “why selected.”
- **Bottom dock:** restricted document/accounting assistant, validation results, before/after extraction, multi-document test output.

## Interactions

Select/resize regions; assign or change fields; create table columns; merge/split fields; ignore areas; compare template versions; test all family samples; accept/reject AI proposals; edit through constrained chat; undo/redo; keyboard shortcuts; draft/save/approve/reject. Every mutation creates a revision operation suitable for replay and audit.

## Data/API design

- Canvas coordinates use page-relative normalized units plus source PDF dimensions.
- A field definition contains semantic ID, source selector, parsing/normalization rule, cardinality, validation links, and confidence rationale.
- A table definition contains header/body boundaries, columns, row continuation, page repetition, subtotal exclusion, and source regions.
- Test results store template version, document hash, extracted structured output, validator results, and diffs from approved golden expectations.
- Approval creates a new immutable version; editing an approved version forks a draft.
- Bulk family approval requires all required samples to pass and no blocking accounting invariant.

## AI boundary

AI may draft selections, mappings, and explanations. It must report what/where/why/confidence/validation impact. It cannot approve, overwrite history, modify raw documents, waive validation, choose a party/ledger irreversibly, or export vouchers. Chat commands compile to visible reversible editor operations.

## Accessibility and safety

Keyboard-accessible canvas alternatives, contrast-safe overlays, focus order, screen-reader field list, autosaved drafts, optimistic concurrency with conflict UI, explicit unsaved-change warnings, and role-gated approvals. Sensitive values are masked according to processing mode while coordinates and structural labels remain usable.
