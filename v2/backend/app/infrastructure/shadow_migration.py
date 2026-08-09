from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from ..domain.mapping import normalize_platform as norm_platform,normalize_text as norm_text


LEGACY_NAMESPACE = UUID("657bbe41-1ac9-54ed-8acd-0d51369dfc29")
TABLES = ("companies", "bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def stable_legacy_uuid(table: str, legacy_id: str, organization_id: UUID) -> UUID:
    return uuid5(LEGACY_NAMESPACE, f"sqlite:{organization_id}:{table}:{legacy_id}")


def read_legacy_rows(path: Path) -> dict[str, list[dict[str, Any]]]:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        return {table: [dict(row) for row in connection.execute(f"SELECT * FROM {table}")] for table in TABLES}
    finally:
        connection.close()


@dataclass
class CategoryResult:
    source_rows: int = 0
    target_candidates: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    duplicates: int = 0
    normalization_conflicts: int = 0
    invalid_rows: int = 0
    warnings: list[str] = field(default_factory=list)


def source_identity(table: str, row: dict[str, Any]) -> str:
    if table == "companies":
        return str(row["name"])
    return str(row["id"])


def source_fingerprint(row: dict[str, Any]) -> str:
    payload = json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ShadowImporter:
    """Idempotent SQLite(read-only) -> PostgreSQL(development-only) importer."""

    def __init__(self, connection: Any, organization_id: UUID, organization_name: str = "Legacy Shadow") -> None:
        self.connection = connection
        self.organization_id = organization_id
        self.organization_name = organization_name

    def import_sqlite(self, sqlite_path: Path) -> dict[str, Any]:
        before = file_sha256(sqlite_path)
        rows = read_legacy_rows(sqlite_path)
        report = {table: CategoryResult(source_rows=len(rows[table]), target_candidates=len(rows[table])) for table in TABLES}
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO organizations(id,name) VALUES(%s,%s) ON CONFLICT(id) DO NOTHING",
                (self.organization_id, self.organization_name),
            )
            company_ids: dict[str, UUID] = {}
            for row in rows["companies"]:
                identity = source_identity("companies", row)
                entity_id = stable_legacy_uuid("companies", identity, self.organization_id)
                self._tenant(cursor,entity_id)
                company_ids[row["name"]] = entity_id
                existed = self._was_imported(cursor, "companies", identity)
                cursor.execute(
                    """INSERT INTO companies(id,organization_id,name,tally_company_name,gstin,state,suspense_ledger,cgst_ledger,sgst_ledger,igst_ledger)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(id) DO UPDATE SET tally_company_name=excluded.tally_company_name,gstin=excluded.gstin,state=excluded.state,
                         suspense_ledger=excluded.suspense_ledger,cgst_ledger=excluded.cgst_ledger,sgst_ledger=excluded.sgst_ledger,igst_ledger=excluded.igst_ledger""",
                    (entity_id, self.organization_id, row["name"], row.get("tally_company_name") or row["name"], row.get("gstin"), row.get("state"),
                     row.get("suspense_ledger") or "Suspense", row.get("cgst_ledger") or "INPUT CGST", row.get("sgst_ledger") or "INPUT SGST", row.get("igst_ledger") or "INPUT IGST"),
                )
                self._record_identity(cursor, "companies", identity, entity_id, entity_id, row)
                report["companies"].updated += int(existed)
                report["companies"].inserted += int(not existed)

            specs = {
                "bank_accounts": ("""INSERT INTO bank_accounts(id,organization_id,company_id,account_hint_token,bank_ledger,notes)
                    VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET account_hint_token=excluded.account_hint_token,bank_ledger=excluded.bank_ledger,notes=excluded.notes""",
                    lambda r: (str(r.get("account_hint") or ""), norm_text(r.get("bank_ledger")), r.get("notes"))),
                "party_ledgers": ("""INSERT INTO party_ledgers(id,organization_id,company_id,platform,party_ledger,party_gstin,state)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,party_ledger=excluded.party_ledger,party_gstin=excluded.party_gstin,state=excluded.state""",
                    lambda r: (norm_platform(r.get("platform")), norm_text(r.get("party_ledger")), r.get("party_gstin"), r.get("state"))),
                "ledger_mappings": ("""INSERT INTO ledger_mappings(id,organization_id,company_id,tool,platform,pattern,voucher_type,ledger,match_type,enabled,notes)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET tool=excluded.tool,platform=excluded.platform,pattern=excluded.pattern,voucher_type=excluded.voucher_type,ledger=excluded.ledger,match_type=excluded.match_type,enabled=excluded.enabled,notes=excluded.notes""",
                    lambda r: (norm_platform(r.get("tool")), norm_platform(r.get("platform")), r.get("pattern") or "", norm_text(r.get("voucher_type")), norm_text(r.get("ledger")), r.get("match_type") or "contains", bool(r.get("enabled", 1)), r.get("notes"))),
                "voucher_rules": ("""INSERT INTO voucher_rules(id,organization_id,company_id,platform,document_type,tally_voucher_type,sign_mode)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,document_type=excluded.document_type,tally_voucher_type=excluded.tally_voucher_type,sign_mode=excluded.sign_mode""",
                    lambda r: (norm_platform(r.get("platform")), norm_text(r.get("pdf_doc_type")), norm_text(r.get("tally_voucher_type")), norm_text(r.get("sign_mode")))),
            }
            for table, (sql, values) in specs.items():
                for row in rows[table]:
                    company_id = company_ids.get(row.get("company_name"))
                    if company_id is None:
                        report[table].invalid_rows += 1
                        continue
                    identity = source_identity(table, row)
                    self._tenant(cursor,company_id)
                    entity_id = stable_legacy_uuid(table, identity, self.organization_id)
                    existed = self._was_imported(cursor, table, identity)
                    cursor.execute(sql, (entity_id, self.organization_id, company_id, *values(row)))
                    self._record_identity(cursor, table, identity, entity_id, company_id, row)
                    report[table].updated += int(existed)
                    report[table].inserted += int(not existed)
                    report[table].normalization_conflicts += self._record_normalizations(cursor, table, identity, row)
            self.connection.commit()
        after = file_sha256(sqlite_path)
        if before != after:
            raise RuntimeError("authoritative SQLite hash changed during shadow import")
        return {"mode": "shadow-import", "sqlite_mode": "read-only-immutable", "sha256_before": before,
                "sha256_after": after, "tables": {name: vars(result) for name, result in report.items()}}

    def _tenant(self,cursor,company_id:UUID) -> None:
        cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(self.organization_id),))
        cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company_id),))

    def _record_identity(self, cursor, table: str, legacy_id: str, entity_id: UUID, company_id: UUID | None, row: dict[str, Any]) -> None:
        cursor.execute(
            """INSERT INTO legacy_identity_map(legacy_source,legacy_table,legacy_id,organization_id,company_id,v2_uuid,source_fingerprint)
               VALUES('sqlite',%s,%s,%s,%s,%s,%s)
               ON CONFLICT(legacy_source,legacy_table,legacy_id,organization_id)
               DO UPDATE SET company_id=excluded.company_id,v2_uuid=excluded.v2_uuid,source_fingerprint=excluded.source_fingerprint,imported_at=now()""",
            (table, legacy_id, self.organization_id, company_id, entity_id, source_fingerprint(row)),
        )

    def _was_imported(self, cursor, table: str, legacy_id: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM legacy_identity_map WHERE legacy_source='sqlite' AND legacy_table=%s AND legacy_id=%s AND organization_id=%s",
            (table, legacy_id, self.organization_id),
        )
        return cursor.fetchone() is not None

    def _record_normalizations(self, cursor, table: str, legacy_id: str, row: dict[str, Any]) -> int:
        changed = 0
        compact_fields = {"platform", "tool"}
        for field_name, source in row.items():
            if not isinstance(source, str):
                continue
            normalized = norm_platform(source) if field_name in compact_fields else norm_text(source)
            if source == normalized:
                continue
            changed += 1
            rule = "legacy norm_platform" if field_name in compact_fields else "legacy norm_text"
            normalization_id = uuid5(LEGACY_NAMESPACE, f"normalization:{self.organization_id}:{table}:{legacy_id}:{field_name}")
            cursor.execute(
                """INSERT INTO migration_normalizations(id,organization_id,legacy_table,legacy_id,field_name,source_value,normalized_value,normalization_rule)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(organization_id,legacy_table,legacy_id,field_name)
                   DO UPDATE SET source_value=excluded.source_value,normalized_value=excluded.normalized_value,normalization_rule=excluded.normalization_rule""",
                (normalization_id, self.organization_id, table, legacy_id, field_name, source, normalized, rule),
            )
        return changed
