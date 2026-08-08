from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def create(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
            CREATE TABLE companies(name TEXT PRIMARY KEY,tally_company_name TEXT,gstin TEXT,state TEXT,suspense_ledger TEXT,cgst_ledger TEXT,sgst_ledger TEXT,igst_ledger TEXT);
            CREATE TABLE bank_accounts(id INTEGER PRIMARY KEY,company_name TEXT,account_hint TEXT,bank_ledger TEXT,notes TEXT);
            CREATE TABLE party_ledgers(id INTEGER PRIMARY KEY,company_name TEXT,platform TEXT,party_ledger TEXT,party_gstin TEXT,state TEXT);
            CREATE TABLE ledger_mappings(id INTEGER PRIMARY KEY,company_name TEXT,tool TEXT,platform TEXT,pattern TEXT,voucher_type TEXT,ledger TEXT,match_type TEXT,enabled INTEGER,notes TEXT);
            CREATE TABLE voucher_rules(id INTEGER PRIMARY KEY,company_name TEXT,platform TEXT,pdf_doc_type TEXT,tally_voucher_type TEXT,sign_mode TEXT);
            INSERT INTO companies VALUES('Synthetic Company','Synthetic Company','','','Suspense','CGST','SGST','IGST');
        """)
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    create(parser.parse_args().path)
