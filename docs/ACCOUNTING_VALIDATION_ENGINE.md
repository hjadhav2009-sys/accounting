# Accounting validation engine

Validators are deterministic and Decimal-based. Required fields can block; quantity totals block on mismatch; line quantity x rate checks run only when marked applicable; every GST bucket is independently checked at its actual rate; invoice totals include unique taxable partitions, taxes, adjustments, and round-off. Blocking findings yield BLOCKED, review findings yield REVIEW, and no findings yield VERIFIED.
