# Bank reconciliation

`BankBalanceValidator` checks `opening + credits - debits = closing`, per-row running-balance continuity, simultaneous debit/credit values, and blank narration. Money uses two-decimal deterministic rounding. Balance failures are blocking; ambiguous row structure is reviewable. The normalized extraction model reserves bank transactions, while automatic bank-format parsing remains routed through the existing legacy boundary.
