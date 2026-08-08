"""Read-only production DB metadata check; never prints private row values."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[2] / "data" / "business_rules.db"
KNOWN_PLATFORMS = (
    "amazon",
    "flipkart",
    "meesho",
    "myntra",
    "meesho_limited",
    "meesho_technologies",
    "valmo",
)


def digest() -> str:
    return hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()


def norm_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm_platform(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def main() -> None:
    before = digest()
    uri = f"file:{DB_PATH.as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    schema = {}
    for table in tables:
        columns = [
            {"name": row[1], "type": row[2], "notnull": bool(row[3]), "default": row[4], "pk": row[5]}
            for row in connection.execute(f"PRAGMA table_info({table})")
        ]
        indexes = []
        for index_row in connection.execute(f"PRAGMA index_list({table})"):
            indexes.append(
                {
                    "name": index_row[1],
                    "unique": bool(index_row[2]),
                    "columns": [
                        item[2]
                        for item in connection.execute(f"PRAGMA index_info({index_row[1]})")
                    ],
                }
            )
        foreign_keys = [
            {"from": row[3], "to_table": row[2], "to": row[4]}
            for row in connection.execute(f"PRAGMA foreign_key_list({table})")
        ]
        schema[table] = {
            "count": connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
        }

    companies = [row[0] for row in connection.execute("SELECT name FROM companies")]
    parties = list(
        connection.execute("SELECT company_name, platform, party_ledger FROM party_ledgers")
    )

    def party_lookup(company: str, platform: str) -> str:
        wanted = norm_platform(platform)
        candidates = (
            (company, wanted),
            ("Default Company", wanted),
            (company, "unknown"),
            ("Default Company", "unknown"),
        )
        for candidate_company, candidate_platform in candidates:
            for row_company, row_platform, row_ledger in parties:
                if (
                    row_company == candidate_company
                    and norm_platform(row_platform) == candidate_platform
                    and norm_text(row_ledger)
                ):
                    return norm_text(row_ledger)
        return "Suspense"

    party_results = [party_lookup(company, platform) for company in companies for platform in KNOWN_PLATFORMS]
    match_types = dict(
        connection.execute(
            "SELECT COALESCE(match_type,''), COUNT(*) FROM ledger_mappings "
            "GROUP BY COALESCE(match_type,'')"
        ).fetchall()
    )
    blank_patterns = connection.execute(
        "SELECT COUNT(*) FROM ledger_mappings WHERE TRIM(COALESCE(pattern,''))=''"
    ).fetchone()[0]
    connection.close()
    after = digest()

    print(
        json.dumps(
            {
                "hash_before": before,
                "hash_after": after,
                "unchanged": before == after,
                "tables": schema,
                "company_records": len(companies),
                "company_name_normalization_anomalies": sum(
                    1 for company in companies if company != norm_text(company)
                ),
                "party_platform_normalization_anomalies": sum(
                    1 for _, platform, _ in parties if platform != norm_platform(platform)
                ),
                "known_party_lookup_combinations": len(party_results),
                "known_party_suspense_results": sum(
                    1 for result in party_results if result.lower() == "suspense"
                ),
                "mapping_match_types": match_types,
                "blank_mapping_patterns": blank_patterns,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
