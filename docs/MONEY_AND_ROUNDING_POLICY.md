# Money and Rounding Policy

- V2 authoritative money uses `Decimal`, serialized as decimal strings and stored as PostgreSQL `numeric(18,2)` unless a domain-specific scale requires more precision.
- Currency is an uppercase ISO-style three-letter code; Phase 1 defaults to INR.
- Final currency values quantize to `0.01` using `ROUND_HALF_UP`.
- Tax rates remain `Decimal` and are never merged merely because they belong to one invoice.
- Default comparison tolerance is one currency minor unit (`0.01`) for V2 domain comparisons. A legacy format may retain its certified tolerance until explicitly migrated.
- Intermediate multiplication should retain additional precision; round at the legally defined line/tax/document boundary, not after arbitrary operations.
- Cross-currency arithmetic is rejected unless an explicit exchange-rate operation exists.

Phase 1 does not convert or alter legacy float calculations. The policy applies when a workflow is deliberately migrated with parity tests.
