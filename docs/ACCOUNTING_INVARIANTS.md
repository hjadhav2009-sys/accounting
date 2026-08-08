# Accounting Invariants

These checks are deterministic and authoritative. AI may propose fields or mappings but must never waive, overwrite, or silently repair a failed invariant.

## Document and line invariants

1. Preserve every GST bucket independently; never collapse 3%, 5%, 12%, 18%, 28%, or other rates into one rate.
2. For each line, `taxable + CGST + SGST + IGST ≈ line total`, using a documented family-specific tolerance. Current marketplace tolerance is 1.00.
3. Where quantity and unit price are authoritative, `quantity × unit price ≈ taxable`, with explicit discount/charge handling.
4. `GST ≈ taxable × rate / 100`, subject only to permitted statutory rounding.
5. Intra-state tax normally has CGST and SGST with equal rates; inter-state tax normally has IGST. Exceptions require explicit evidence and review.
6. Sum of parsed line quantities equals displayed quantity total when the document supplies one.
7. Sum of taxable amounts per GST rate/HSN agrees with displayed tax summaries when supplied.
8. `subtotal + charges - discounts ± round-off = document total`.
9. Invoice/reference number, supplier, date, currency, and document type must be present or explicitly reviewed; never use today's date silently for export.
10. Source values, normalized values, calculations, and corrections retain provenance.

## Voucher invariants

- Marketplace Tax Invoice maps to Purchase unless an explicit approved company rule says otherwise.
- Marketplace Credit Note maps to Debit Note with reversed signs.
- A known platform must never export with Suspense as party ledger.
- Unknown expense ledger remains REVIEW/Suspense and is excluded under the safe default.
- Party plus expense/tax ledger entries sum to zero for every voucher, within currency precision.
- Invoice number is retained in `VOUCHERNUMBER`, `BASICVOUCHERNUMBER`, `REFERENCE`, and `BASICREFERENCE` unless a documented Tally constraint requires transformation.
- XML special characters are escaped and output is well-formed.
- No zero-amount or parse-failed row may be exported without explicit reviewed policy.

## Bank invariants

- A transaction cannot be both a deposit and withdrawal unless the format explicitly models corrections.
- Deposit becomes Receipt; withdrawal becomes Payment.
- Counter-ledger amount plus bank-ledger amount equals zero per voucher.
- Blank narration patterns are never persisted or matched.
- Unmatched narration remains review/Suspense according to company policy.
- The selected bank ledger must correspond to the detected account, not merely the first configured account.
- Statement-level reconciliation: `opening balance + credits - debits = closing balance` within statement currency precision.
- Running balances must reconcile in statement order where available.

## Database and export invariants

- Company-specific rules precede defaults.
- Whitespace/newline/case normalization must not turn a known supplier into unknown/Suspense.
- Disabled rules never match; match ordering is deterministic and explainable.
- Money is represented with fixed decimal types in V2, never binary floating point as the source of truth.
- Duplicate or replayed exports are detected and require an auditable override.
- An invariant failure blocks export and routes the job to review. Human override, if permitted, records actor, reason, timestamp, before/after values, and affected checks.
