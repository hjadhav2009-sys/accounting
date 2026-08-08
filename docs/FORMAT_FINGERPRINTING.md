# Format fingerprinting

Fingerprints hash normalized anchors, page count, rounded dimensions and detected table headers; filenames are excluded. Similarity is measurable: 70% anchor Jaccard, 15% page-count and 15% dimension score. Signature/features persist per tenant/document.

Approved deterministic legacy routes resolve a tenant format family and approved version-1 adapter definition without copying parser rules. Unknown fingerprints remain unassigned and appear in the read-only format-health view as Phase 4 input.
