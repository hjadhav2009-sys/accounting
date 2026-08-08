# Hybrid AI V2 Notes

Planned flow for unknown/changed document formats:

1. Duplicate check locally (SHA-256 + business identity checks).
2. Native PDF extraction.
3. Known template/fingerprint match.
4. Local privacy scanner identifies sensitive fields.
5. Create redacted/minimized representation with placeholders.
6. Local model handles simple classification/mapping when capable.
7. Difficult cases may be sent to Cloudflare Workers AI, subject to quota/privacy policy.
8. Cloud/local AI returns a proposed schema/template only.
9. Local deterministic validator recomputes quantity, taxable values, GST buckets, totals, bank balances and reconciliation.
10. Template Studio shows exactly what was selected and why.
11. Human can correct through visual editing or domain-limited chat.
12. Approved template is versioned and reused for later documents.

Cloud quota behavior should be fail-closed for cost:
- warn before configured free-tier safety threshold
- never auto-upgrade to a paid plan
- when threshold is reached, switch to local-only / queue-until-reset according to admin choice
- display reset time and pending jobs
