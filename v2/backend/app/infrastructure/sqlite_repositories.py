from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shared import database as legacy_db


class LegacySQLiteRepositories:
    """Compatibility facade over certified database functions.

    SQLite remains authoritative. This adapter deliberately delegates rather
    than reimplementing normalization, fallback, or mapping behavior.
    """

    def __init__(self, database_module=legacy_db) -> None:
        self._db = database_module

    def list_companies(self) -> Sequence[dict[str, Any]]:
        return self._db.companies()

    def get_company(self, name: str) -> dict[str, Any] | None:
        return self._db.company(name) or None

    def list_bank_accounts(self, company_name: str) -> Sequence[dict[str, Any]]:
        return self._db.df_table("bank_accounts", company_name).to_dict("records")

    def party_ledger(self, company_name: str, platform: str) -> str:
        return self._db.party_ledger(company_name, platform)

    def map_ledger(
        self,
        company_name: str,
        tool: str,
        platform: str,
        description: str,
        voucher_type: str = "",
    ) -> tuple[str, str]:
        return self._db.map_ledger(company_name, tool, platform, description, voucher_type)

    def get_rule(self, company_name: str, platform: str, document_type: str) -> dict[str, Any]:
        return dict(self._db.voucher_rule(company_name, platform, document_type))
