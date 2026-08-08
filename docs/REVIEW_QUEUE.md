# Review queue

Review tasks persist tenant/company/document, reason, severity, detail, assignee, state, resolution note, resolver and timestamps. Reasons cover `UNKNOWN_FORMAT`, OCR confidence/failure, quantity/GST/total/bank mismatches, unknown ledger, possible duplicate and missing required fields.

The API and frontend filter by company context, reason, severity, status, assignee and date with URL state. Every task navigates to document evidence; resolution requires a note. Review Format remains read-only until Phase 4.
