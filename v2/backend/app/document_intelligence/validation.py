from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Protocol

from .models import AccountingValidationReport, ErrorCode, Severity, ValidationFinding


CENT = Decimal("0.01")


def decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def money(value: Any) -> Decimal:
    return decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class Validator(Protocol):
    name: str
    def validate(self, payload: dict[str, Any]) -> tuple[ValidationFinding, ...]: ...


@dataclass(frozen=True)
class RequiredFieldValidator:
    required: tuple[str, ...]
    name: str = "RequiredFieldValidator"

    def validate(self, payload: dict[str, Any]) -> tuple[ValidationFinding, ...]:
        return tuple(ValidationFinding(self.name, "BLOCKED", Severity.BLOCKING, f"Required field is missing: {field}",
                                       error_code=ErrorCode.REQUIRED_FIELD_MISSING)
                     for field in self.required if payload.get(field) in (None, "", (), []))


@dataclass(frozen=True)
class QuantityValidator:
    tolerance: Decimal = CENT
    name: str = "QuantityValidator"

    def validate(self, payload: dict[str, Any]) -> tuple[ValidationFinding, ...]:
        if payload.get("displayed_total_quantity") is None:
            return ()
        actual = sum((decimal(item.get("quantity")) for item in payload.get("items", ())), Decimal("0"))
        expected = decimal(payload["displayed_total_quantity"])
        difference = actual - expected
        if abs(difference) <= self.tolerance:
            return ()
        return (ValidationFinding(self.name, "BLOCKED", Severity.BLOCKING, "Item quantities do not reconcile with the displayed total",
                                  str(expected), str(actual), str(difference), error_code=ErrorCode.QUANTITY_MISMATCH),)


@dataclass(frozen=True)
class LineAmountValidator:
    tolerance: Decimal = CENT
    name: str = "LineAmountValidator"

    def validate(self, payload: dict[str, Any]) -> tuple[ValidationFinding, ...]:
        findings: list[ValidationFinding] = []
        for index, item in enumerate(payload.get("items", ())):
            if not item.get("validate_line_formula", False):
                continue
            expected = money(decimal(item.get("quantity")) * decimal(item.get("unit_rate")))
            actual = money(item.get("taxable"))
            if abs(expected - actual) > self.tolerance:
                findings.append(ValidationFinding(self.name, "REVIEW", Severity.REVIEW,
                    f"Line {index + 1} quantity × rate differs from taxable amount", str(expected), str(actual), str(actual - expected)))
        return tuple(findings)


@dataclass(frozen=True)
class TaxBucketValidator:
    tolerance: Decimal = CENT
    name: str = "TaxBucketValidator"

    def validate(self, payload: dict[str, Any]) -> tuple[ValidationFinding, ...]:
        findings: list[ValidationFinding] = []
        for index, bucket in enumerate(payload.get("tax_buckets", ())):
            expected = money(decimal(bucket.get("taxable")) * decimal(bucket.get("rate")) / Decimal("100"))
            actual = money(bucket.get("tax"))
            if abs(expected - actual) > self.tolerance:
                findings.append(ValidationFinding(self.name, "BLOCKED", Severity.BLOCKING,
                    f"Tax bucket {index + 1} does not reconcile", str(expected), str(actual), str(actual - expected),
                    error_code=ErrorCode.GST_MISMATCH))
        return tuple(findings)


@dataclass(frozen=True)
class InvoiceTotalValidator:
    tolerance: Decimal = CENT
    name: str = "InvoiceTotalValidator"

    def validate(self, payload: dict[str, Any]) -> tuple[ValidationFinding, ...]:
        if payload.get("invoice_total") is None:
            return ()
        if payload.get("taxable_total") is not None:
            taxable = money(payload["taxable_total"])
        elif payload.get("items"):
            taxable = sum((money(item.get("taxable")) for item in payload.get("items", ())), Decimal("0"))
        else:
            # CGST and SGST buckets often repeat the same taxable base. Count each
            # rate/HSN/base partition once while preserving unlimited GST rates.
            partitions = {
                (str(bucket.get("rate") or ""), str(bucket.get("hsn_sac") or ""), money(bucket.get("taxable")))
                for bucket in payload.get("tax_buckets", ())
            }
            taxable = sum((partition[2] for partition in partitions), Decimal("0"))
        tax = sum((money(bucket.get("tax")) for bucket in payload.get("tax_buckets", ())), Decimal("0"))
        adjustments = money(payload.get("adjustments"))
        round_off = money(payload.get("round_off"))
        expected = money(taxable + tax + adjustments + round_off)
        actual = money(payload["invoice_total"])
        if abs(expected - actual) <= self.tolerance:
            return ()
        return (ValidationFinding(self.name, "BLOCKED", Severity.BLOCKING, "Invoice total does not reconcile",
                                  str(expected), str(actual), str(actual - expected), error_code=ErrorCode.INVOICE_TOTAL_MISMATCH),)


@dataclass(frozen=True)
class BankBalanceValidator:
    tolerance: Decimal = CENT
    name: str = "BankBalanceValidator"

    def validate(self, payload: dict[str, Any]) -> tuple[ValidationFinding, ...]:
        if payload.get("opening_balance") is None or payload.get("closing_balance") is None:
            return ()
        opening = money(payload["opening_balance"])
        transactions = payload.get("bank_transactions", ())
        credits = sum((money(row.get("credit")) for row in transactions), Decimal("0"))
        debits = sum((money(row.get("debit")) for row in transactions), Decimal("0"))
        expected = money(opening + credits - debits)
        actual = money(payload["closing_balance"])
        findings: list[ValidationFinding] = []
        if abs(expected - actual) > self.tolerance:
            findings.append(ValidationFinding(self.name, "BLOCKED", Severity.BLOCKING, "Bank closing balance does not reconcile",
                str(expected), str(actual), str(actual - expected), error_code=ErrorCode.BANK_BALANCE_MISMATCH))
        previous = opening
        for index, row in enumerate(transactions):
            debit, credit = money(row.get("debit")), money(row.get("credit"))
            if debit and credit:
                findings.append(ValidationFinding(self.name, "REVIEW", Severity.REVIEW,
                    f"Transaction {index + 1} contains both debit and credit"))
            if not str(row.get("narration") or "").strip():
                findings.append(ValidationFinding(self.name, "REVIEW", Severity.REVIEW,
                    f"Transaction {index + 1} has blank narration"))
            calculated = money(previous + credit - debit)
            if row.get("balance") is not None and abs(calculated - money(row["balance"])) > self.tolerance:
                findings.append(ValidationFinding(self.name, "BLOCKED", Severity.BLOCKING,
                    f"Transaction {index + 1} balance continuity failed", str(calculated), str(money(row["balance"])),
                    str(money(row["balance"]) - calculated), error_code=ErrorCode.BANK_BALANCE_MISMATCH))
            previous = money(row.get("balance")) if row.get("balance") is not None else calculated
        return tuple(findings)


class AccountingValidationEngine:
    def __init__(self, validators: tuple[Validator, ...] | None = None) -> None:
        self.validators = validators or (QuantityValidator(), LineAmountValidator(), TaxBucketValidator(), InvoiceTotalValidator(), BankBalanceValidator())

    def validate(self, payload: dict[str, Any]) -> AccountingValidationReport:
        findings = tuple(finding for validator in self.validators for finding in validator.validate(payload))
        if any(finding.severity is Severity.BLOCKING for finding in findings):
            status = "BLOCKED"
        elif findings:
            status = "REVIEW"
        else:
            status = "VERIFIED"
        calculations = {
            "taxable_total": str(sum((money(bucket.get("taxable")) for bucket in payload.get("tax_buckets", ())), Decimal("0"))),
            "tax_total": str(sum((money(bucket.get("tax")) for bucket in payload.get("tax_buckets", ())), Decimal("0"))),
        }
        return AccountingValidationReport(status, findings, calculations)
