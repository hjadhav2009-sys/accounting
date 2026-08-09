from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from ..domain.mapping import normalize_platform as norm_platform,normalize_text as norm_text

from ..infrastructure.shadow_migration import (
    ShadowImporter, file_sha256, read_legacy_rows, source_fingerprint, source_identity, stable_legacy_uuid,
)


EXPECTED_SQLITE_SHA256 = "87E55412BB10C7D953E3F971F45F455E3A7769D179C9DE2D84575BF47616AE5E"
TABLES = ("companies", "bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules")


def _company(row: dict[str, Any]) -> str:
    return str(row.get("name") if "name" in row and "company_name" not in row else row.get("company_name") or "")


def _natural(table: str, row: dict[str, Any]) -> tuple[Any, ...]:
    if table == "companies": return (norm_text(row.get("name")),)
    if table == "bank_accounts": return (str(row.get("account_hint") or ""), norm_text(row.get("bank_ledger")))
    if table == "party_ledgers": return (norm_platform(row.get("platform")),)
    if table == "ledger_mappings": return (norm_platform(row.get("tool")), norm_platform(row.get("platform")),
        norm_text(row.get("pattern")), norm_text(row.get("voucher_type")))
    return (norm_platform(row.get("platform")), norm_text(row.get("pdf_doc_type")))


def _normalization_changes(row: dict[str, Any]) -> int:
    changes = 0
    for name, value in row.items():
        if not isinstance(value, str): continue
        normalized = norm_platform(value) if name in {"tool", "platform"} else norm_text(value)
        changes += int(value != normalized)
    return changes


class ExistingDataMigration:
    """Preview-first immutable SQLite import. The source path is never opened writable."""

    def __init__(self, connection: Any, organization_id: UUID, source_path: Path,
                 expected_hash: str = EXPECTED_SQLITE_SHA256) -> None:
        self.connection, self.organization_id = connection, organization_id
        self.source_path, self.expected_hash = source_path, expected_hash

    def preview(self) -> dict[str, Any]:
        before = file_sha256(self.source_path)
        rows = read_legacy_rows(self.source_path)
        categories: dict[str, dict[str, Any]] = {}
        by_company: dict[str, Counter[str]] = defaultdict(Counter)
        company_ids = {row["name"]: stable_legacy_uuid("companies", row["name"], self.organization_id)
                       for row in rows["companies"]}
        with self.connection.cursor() as cursor:
            for table in TABLES:
                duplicate_keys = Counter((_company(row), _natural(table, row)) for row in rows[table])
                summary = Counter(source_rows=len(rows[table]), candidate_target_rows=len(rows[table]))
                for row in rows[table]:
                    company_name = _company(row); identity = source_identity(table, row)
                    company_id = company_ids.get(company_name)
                    if company_id is None:
                        summary["invalid"] += 1; by_company[company_name or "(missing)"]["invalid"] += 1; continue
                    cursor.execute("SELECT set_config('app.organization_id',%s,true)", (str(self.organization_id),))
                    cursor.execute("SELECT set_config('app.company_id',%s,true)", (str(company_id),))
                    if duplicate_keys[(company_name, _natural(table, row))] > 1:
                        summary["duplicates"] += 1; by_company[company_name]["duplicates"] += 1; continue
                    entity_id = stable_legacy_uuid(table, identity, self.organization_id)
                    if self._target_collision(cursor, table, row, company_id, entity_id):
                        summary["conflicts"] += 1; by_company[company_name]["conflicts"] += 1; continue
                    cursor.execute("""SELECT source_fingerprint FROM legacy_identity_map
                        WHERE legacy_source='sqlite' AND legacy_table=%s AND legacy_id=%s AND organization_id=%s""",
                        (table, identity, self.organization_id))
                    prior = cursor.fetchone()
                    changes = _normalization_changes(row)
                    if prior and prior[0] == source_fingerprint(row): summary["existing_exact"] += 1
                    elif changes: summary["normalized"] += 1
                    else: summary["exact"] += 1
                    summary["normalization_changes"] += changes
                    by_company[company_name][table] += 1
                for key in ("exact", "normalized", "existing_exact", "duplicates", "conflicts", "invalid", "missing", "normalization_changes"):
                    summary.setdefault(key, 0)
                categories[table] = dict(summary)
        after = file_sha256(self.source_path)
        if before != after: raise RuntimeError("protected SQLite changed during migration preview")
        conflicts=sum(item["conflicts"] for item in categories.values());invalid=sum(item["invalid"] for item in categories.values())
        duplicates=sum(item["duplicates"] for item in categories.values());blocked=bool(conflicts or invalid or duplicates)
        blocking_reasons=[]
        if conflicts:blocking_reasons.append("TARGET_NATURAL_KEY_CONFLICTS")
        if duplicates:blocking_reasons.append("DUPLICATE_SOURCE_NATURAL_KEYS")
        if invalid:blocking_reasons.append("INVALID_SOURCE_OWNERSHIP")
        return {"mode": "PREVIEW", "sqlite_access": "read-only-immutable", "source_file": str(self.source_path),
            "source_sha256": before, "expected_sha256": self.expected_hash, "hash_matches_expected": before == self.expected_hash,
            "source_sha256_after": after, "categories": categories,
            "company_counts": {name: dict(sorted(counts.items())) for name, counts in sorted(by_company.items())},
            "totals": {table: len(rows[table]) for table in TABLES}, "apply_allowed": not blocked,
            "blocking_reasons": blocking_reasons}

    @staticmethod
    def _target_collision(cursor, table: str, row: dict[str, Any], company_id: UUID, entity_id: UUID) -> bool:
        if table == "companies":
            # The organization is enforced by RLS; use the source name without accepting a caller-supplied tenant.
            cursor.execute("SELECT 1 FROM companies WHERE name=%s AND id<>%s", (norm_text(row.get("name")), entity_id))
        elif table == "bank_accounts":
            cursor.execute("""SELECT 1 FROM bank_accounts WHERE company_id=%s AND account_hint_token=%s
                AND bank_ledger=%s AND id<>%s""", (company_id, str(row.get("account_hint") or ""),
                norm_text(row.get("bank_ledger")), entity_id))
        elif table == "party_ledgers":
            cursor.execute("SELECT 1 FROM party_ledgers WHERE company_id=%s AND platform=%s AND id<>%s",
                           (company_id, norm_platform(row.get("platform")), entity_id))
        elif table == "ledger_mappings":
            cursor.execute("""SELECT 1 FROM ledger_mappings WHERE company_id=%s AND tool=%s AND platform=%s
                AND pattern=%s AND voucher_type=%s AND id<>%s""", (company_id, norm_platform(row.get("tool")),
                norm_platform(row.get("platform")), str(row.get("pattern") or ""), norm_text(row.get("voucher_type")), entity_id))
        else:
            cursor.execute("""SELECT 1 FROM voucher_rules WHERE company_id=%s AND platform=%s
                AND document_type=%s AND id<>%s""", (company_id, norm_platform(row.get("platform")),
                norm_text(row.get("pdf_doc_type")), entity_id))
        return cursor.fetchone() is not None

    def apply(self, organization_name: str, preview_sha256: str | None = None) -> dict[str, Any]:
        before = file_sha256(self.source_path)
        captured_hash = preview_sha256 or self.expected_hash
        if before != captured_hash: raise RuntimeError("protected SQLite changed after migration preview")
        report = ShadowImporter(self.connection, self.organization_id, organization_name).import_sqlite(self.source_path)
        source_rows=read_legacy_rows(self.source_path)
        report["company_ids"]={row["name"]:str(stable_legacy_uuid("companies",row["name"],self.organization_id))
                               for row in source_rows["companies"]}
        report["imported_companies"]=[]
        for company in source_rows["companies"]:
            name=company["name"]
            counts={table:sum(1 for row in source_rows[table] if _company(row)==name) for table in TABLES}
            report["imported_companies"].append({"id":report["company_ids"][name],"name":name,
                "counts":counts,"total_records":sum(counts.values())})
        report["preview_sha256"]=captured_hash
        after = file_sha256(self.source_path)
        if before != after: raise RuntimeError("protected SQLite changed during migration")
        report["second_run_duplicates"] = sum(item["duplicates"] for item in report["tables"].values())
        report["unchanged"] = before == after
        return report
