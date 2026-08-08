from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from shared.database import norm_platform, norm_text

from ..services.parity import ParityStatus, classify
from .migration_verifier import DEFAULT_SQLITE
from .postgres import PostgresRepositories, psycopg_connection_factory
from .shadow_migration import file_sha256, read_legacy_rows


class ReadOnlyLegacyData:
    """Certified-behaviour reader over immutable SQLite rows; it never calls init_db."""

    def __init__(self, path: Path) -> None:
        self.rows = read_legacy_rows(path)

    def company(self, name: str) -> dict[str, Any] | None:
        wanted = norm_text(name)
        return next((row for row in self.rows["companies"] if row["name"] == wanted), None)

    def party_ledger(self, company_name: str, platform: str) -> str:
        wanted_company = norm_text(company_name)
        wanted_platform = norm_platform(platform)
        company_names = [wanted_company] + ([] if wanted_company == "Default Company" else ["Default Company"])
        for candidate_platform in (wanted_platform, "unknown"):
            for candidate_company in company_names:
                for row in self.rows["party_ledgers"]:
                    if row["company_name"] == candidate_company and norm_platform(row["platform"]) == candidate_platform:
                        value = norm_text(row.get("party_ledger"))
                        if value:
                            return value
        return "Suspense"

    def map_ledger(self, company_name: str, tool: str, platform: str, description: str, voucher_type: str = "") -> tuple[str, str]:
        wanted_company = norm_text(company_name)
        wanted_tool = norm_platform(tool)
        wanted_platform = norm_platform(platform)
        wanted_voucher = norm_text(voucher_type).lower()
        description_lower = str(description or "").lower()
        company = self.company(wanted_company) or {}
        suspense = company.get("suspense_ledger") or "Suspense"
        company_names = [wanted_company] + ([] if wanted_company == "Default Company" else ["Default Company"])
        for candidate_company in company_names:
            candidates = [row for row in self.rows["ledger_mappings"]
                          if row["company_name"] == candidate_company
                          and norm_platform(row.get("tool")) == wanted_tool and bool(row.get("enabled", 1))]
            for row in sorted(candidates, key=lambda item: len(str(item.get("pattern") or "")), reverse=True):
                row_platform = norm_platform(row.get("platform"))
                if row_platform and wanted_platform and row_platform not in {wanted_platform, "all"}:
                    continue
                row_voucher = norm_text(row.get("voucher_type")).lower()
                if row_voucher and wanted_voucher and row_voucher != wanted_voucher:
                    continue
                pattern = str(row.get("pattern") or "")
                if pattern and pattern.lower() in description_lower:
                    return norm_text(row.get("ledger")) or suspense, pattern
        return suspense, "UNMATCHED_TO_SUSPENSE"

    def voucher_rule(self, company_name: str, platform: str, document_type: str) -> tuple[str, str]:
        wanted_company = norm_text(company_name)
        company_names = [wanted_company] + ([] if wanted_company == "Default Company" else ["Default Company"])
        for candidate_company in company_names:
            for row in self.rows["voucher_rules"]:
                if (row["company_name"] == candidate_company
                        and norm_platform(row["platform"]) == norm_platform(platform)
                        and norm_text(row["pdf_doc_type"]) == norm_text(document_type)):
                    return row["tally_voucher_type"], row["sign_mode"]
        if str(document_type).lower() == "credit note":
            return "Debit Note", "reverse"
        return "Purchase", "charge"


def certify(sqlite_path: Path, database_url: str, organization_id: UUID) -> dict[str, Any]:
    before = file_sha256(sqlite_path)
    legacy = ReadOnlyLegacyData(sqlite_path)
    postgres = PostgresRepositories(psycopg_connection_factory(database_url), organization_id)
    statuses: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    observations: list[tuple[str, str]] = []

    def compare(category: str, authoritative: Any, shadow: Any) -> None:
        statuses[classify(authoritative, shadow).value] += 1
        categories[category] += 1
        observations.append((category, classify(authoritative, shadow).value))

    company_fields = ("name", "tally_company_name", "gstin", "state", "suspense_ledger", "cgst_ledger", "sgst_ledger", "igst_ledger")
    for row in legacy.rows["companies"]:
        shadow = postgres.get_company(row["name"])
        compare("company", tuple(row.get(k) for k in company_fields), tuple((shadow or {}).get(k) for k in company_fields))
        normalized_shadow = postgres.get_company(f"  {row['name']}  ")
        compare("normalization", row["name"], (normalized_shadow or {}).get("name"))

    for company_name in {row["company_name"] for row in legacy.rows["bank_accounts"]}:
        expected = sorted((str(row.get("account_hint") or ""), norm_text(row.get("bank_ledger")), row.get("notes"))
                          for row in legacy.rows["bank_accounts"] if row["company_name"] == company_name)
        actual = sorted((str(row.get("account_hint_token") or ""), norm_text(row.get("bank_ledger")), row.get("notes"))
                        for row in postgres.list_bank_accounts(company_name))
        status = classify(expected, actual).value
        statuses[status] += len(expected) if expected == actual else 1
        categories["bank_account"] += len(expected) if expected == actual else 1
        observations.extend(("bank_account", status) for _ in range(len(expected) if expected == actual else 1))

    for row in legacy.rows["party_ledgers"]:
        compare("party_ledger", legacy.party_ledger(row["company_name"], row["platform"]),
                postgres.party_ledger(row["company_name"], row["platform"]))
        noisy_platform = f" {str(row['platform']).upper()}\n"
        compare("normalization", legacy.party_ledger(row["company_name"], noisy_platform),
                postgres.party_ledger(row["company_name"], noisy_platform))

    for row in legacy.rows["ledger_mappings"]:
        description = f"synthetic-prefix {row['pattern']} synthetic-suffix"
        args = (row["company_name"], row["tool"], row["platform"], description, row.get("voucher_type") or "")
        compare("bank_mapping" if norm_platform(row["tool"]) == "bank" else "marketplace_mapping",
                legacy.map_ledger(*args), postgres.map_ledger(*args))

    for row in legacy.rows["voucher_rules"]:
        expected = legacy.voucher_rule(row["company_name"], row["platform"], row["pdf_doc_type"])
        actual_row = postgres.get_rule(row["company_name"], row["platform"], row["pdf_doc_type"])
        compare("voucher_rule", expected, (actual_row.get("tally_voucher_type"), actual_row.get("sign_mode")))

    after = file_sha256(sqlite_path)
    if before != after:
        raise RuntimeError("authoritative SQLite changed during parity certification")
    connection = psycopg_connection_factory(database_url)()
    try:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO parity_observations(id,organization_id,query_type,result,source_reference)
                   VALUES(%s,%s,%s,%s,'phase2b-runtime')""",
                [(uuid4(), organization_id, category, status) for category, status in observations],
            )
        connection.commit()
    finally:
        connection.close()
    for status in ParityStatus:
        statuses.setdefault(status.value, 0)
    return {
        "sqlite_mode": "read-only-immutable",
        "sha256_before": before,
        "sha256_after": after,
        "comparisons": sum(statuses.values()),
        "categories": dict(sorted(categories.items())),
        "results": dict(sorted(statuses.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Live SQLite/PostgreSQL shadow parity certification.")
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--organization-id", type=UUID, required=True)
    args = parser.parse_args()
    print(json.dumps(certify(args.sqlite, args.database_url, args.organization_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
