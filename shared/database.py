
from pathlib import Path
import re
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "business_rules.db"

def norm_platform(x):
    return re.sub(r"\s+", "", str(x or "")).strip().lower()

def norm_text(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()



def normalize_existing_data(conn):
    q = conn.cursor()
    for table in ["party_ledgers", "ledger_mappings", "voucher_rules"]:
        try:
            q.execute(f"""UPDATE {table}
                          SET platform=LOWER(TRIM(REPLACE(REPLACE(REPLACE(COALESCE(platform,''), CHAR(10), ''), CHAR(13), ''), CHAR(9), '')))""")
        except Exception:
            pass
    try:
        q.execute("""UPDATE ledger_mappings
                     SET tool=LOWER(TRIM(REPLACE(REPLACE(REPLACE(COALESCE(tool,''), CHAR(10), ''), CHAR(13), ''), CHAR(9), '')))""")
    except Exception:
        pass
    try:
        q.execute("""UPDATE party_ledgers
                     SET party_ledger=TRIM(REPLACE(REPLACE(REPLACE(COALESCE(party_ledger,''), CHAR(10), ' '), CHAR(13), ' '), CHAR(9), ' '))""")
    except Exception:
        pass
    try:
        q.execute("""UPDATE companies
                     SET tally_company_name=TRIM(REPLACE(REPLACE(REPLACE(COALESCE(tally_company_name,''), CHAR(10), ' '), CHAR(13), ' '), CHAR(9), ' ')),
                         suspense_ledger=TRIM(REPLACE(REPLACE(REPLACE(COALESCE(suspense_ledger,''), CHAR(10), ' '), CHAR(13), ' '), CHAR(9), ' ')),
                         cgst_ledger=TRIM(REPLACE(REPLACE(REPLACE(COALESCE(cgst_ledger,''), CHAR(10), ' '), CHAR(13), ' '), CHAR(9), ' ')),
                         sgst_ledger=TRIM(REPLACE(REPLACE(REPLACE(COALESCE(sgst_ledger,''), CHAR(10), ' '), CHAR(13), ' '), CHAR(9), ' ')),
                         igst_ledger=TRIM(REPLACE(REPLACE(REPLACE(COALESCE(igst_ledger,''), CHAR(10), ' '), CHAR(13), ' '), CHAR(9), ' '))""")
    except Exception:
        pass
    conn.commit()


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _dedupe_and_index(conn):
    q = conn.cursor()
    q.execute("""DELETE FROM bank_accounts
                 WHERE id NOT IN (
                   SELECT MIN(id) FROM bank_accounts
                   GROUP BY company_name, account_hint, bank_ledger
                 )""")
    q.execute("""DELETE FROM party_ledgers
                 WHERE id NOT IN (
                   SELECT MIN(id) FROM party_ledgers
                   GROUP BY company_name, platform
                 )""")
    q.execute("""DELETE FROM ledger_mappings
                 WHERE id NOT IN (
                   SELECT MIN(id) FROM ledger_mappings
                   GROUP BY company_name, tool, platform, pattern, voucher_type
                 )""")
    q.execute("""DELETE FROM voucher_rules
                 WHERE id NOT IN (
                   SELECT MIN(id) FROM voucher_rules
                   GROUP BY company_name, platform, pdf_doc_type
                 )""")
    q.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_bank_accounts ON bank_accounts(company_name, account_hint, bank_ledger)")
    q.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_party_ledgers ON party_ledgers(company_name, platform)")
    q.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ledger_mappings ON ledger_mappings(company_name, tool, platform, pattern, voucher_type)")
    q.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_voucher_rules ON voucher_rules(company_name, platform, pdf_doc_type)")
    conn.commit()


def init_db():
    conn = connect()
    q = conn.cursor()
    q.execute("""CREATE TABLE IF NOT EXISTS companies(
        name TEXT PRIMARY KEY,
        tally_company_name TEXT,
        gstin TEXT,
        state TEXT,
        suspense_ledger TEXT DEFAULT 'Suspense',
        cgst_ledger TEXT DEFAULT 'INPUT CGST',
        sgst_ledger TEXT DEFAULT 'INPUT SGST',
        igst_ledger TEXT DEFAULT 'INPUT IGST'
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS bank_accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        account_hint TEXT,
        bank_ledger TEXT,
        notes TEXT
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS party_ledgers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        platform TEXT,
        party_ledger TEXT,
        party_gstin TEXT,
        state TEXT
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS ledger_mappings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        tool TEXT,
        platform TEXT,
        pattern TEXT,
        voucher_type TEXT DEFAULT '',
        ledger TEXT,
        match_type TEXT DEFAULT 'contains',
        enabled INTEGER DEFAULT 1,
        notes TEXT
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS voucher_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        platform TEXT,
        pdf_doc_type TEXT,
        tally_voucher_type TEXT,
        sign_mode TEXT
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS import_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        tool TEXT,
        platform TEXT,
        invoice_no TEXT,
        voucher_type TEXT,
        voucher_date TEXT,
        amount REAL,
        source_file TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    _dedupe_and_index(conn)
    seed_defaults(conn)
    normalize_existing_data(conn)
    conn.close()

def seed_defaults(conn):
    q = conn.cursor()
    q.execute("INSERT OR IGNORE INTO companies(name,tally_company_name,gstin,state,suspense_ledger,cgst_ledger,sgst_ledger,igst_ledger) VALUES(?,?,?,?,?,?,?,?)",
              ("Default Company", "Default Company", "", "", "Suspense", "INPUT CGST", "INPUT SGST", "INPUT IGST"))

    # Public source must never carry real account data.  Existing databases are
    # authoritative and are left alone; only a genuinely empty/default install
    # receives this unmistakably synthetic placeholder.
    existing_default_account = q.execute(
        "SELECT 1 FROM bank_accounts WHERE company_name=? LIMIT 1",
        ("Default Company",),
    ).fetchone()
    if existing_default_account is None:
        q.execute(
            "INSERT OR IGNORE INTO bank_accounts(company_name,account_hint,bank_ledger,notes) VALUES(?,?,?,?)",
            ("Default Company", "SYNTHETIC-ACCOUNT", "SYNTHETIC BANK LEDGER", "Synthetic public default"),
        )

    parties = {
        "amazon": "AMAZON SELLER SERVICES PVT LTD",
        "flipkart": "FLIPKART INTERNET PVT Ltd -Ka",
        "meesho": "MEESHO TECHNOLOGIES PRIVATE LIMITED",
        "meesho_limited": "MEESHO LIMITED",
        "meesho_technologies": "MEESHO TECHNOLOGIES PRIVATE LIMITED",
        "valmo": "VALMO TRANSPORTATION PRIVATE LIMITED",
        "myntra": "MYNTRA DESIGNS PVT LTD.",
        "unknown": "Suspense",
    }
    for platform, ledger in parties.items():
        q.execute("INSERT OR IGNORE INTO party_ledgers(company_name,platform,party_ledger) VALUES(?,?,?)",
                  ("Default Company", platform, ledger))

    mappings = [
        ("bank","","FLIPKART INTERNET PRIVATE","Selling Through Flipkart"),
        ("bank","","CASHFREE PAYMENTS ESCROW ACC","Selling Through Meesho"),
        ("bank","","CASHFREE PAYMENTS ESCROWACC","Selling Through Meesho"),
        ("bank","","MEESHO TECHNOLOGIES PRIVATE","Selling Through Meesho"),
        ("bank","","Amazon Sel","Selling Through Amazon"),
        ("bank","","INTERNAL AC FOR INTERMEDIERY","Selling Through Amazon"),
        ("bank","","MYNTRA DESIGNS PRIVATE","Selling Through Myntra"),

        ("marketplace","amazon","Sale of space for advertisement","Sale of space for advertisement-amazon"),
        ("marketplace","amazon","Sale of space for advertisement on amazon.in","Sale of space for advertisement-amazon"),
        ("marketplace","amazon","Storage Fee","Storage Fee-Amazon1"),
        ("marketplace","amazon","FBA Weight Handling Shipping Fee","FBA Weight Handling Shipping Fee-Amazon1"),
        ("marketplace","amazon","Shipping Chargeback Fee","Shipping Chargeback Fee-Amazon1"),
        ("marketplace","amazon","Giftwrap Fee","Giftwrap Fee-Amazo1"),
        ("marketplace","amazon","FBA Pick and Pack Fee","FBA Pick and Pack Fee-Amazon1"),
        ("marketplace","amazon","Removal Fee","Removal Fee-Amazon1"),
        ("marketplace","amazon","Fixed Closing Fee","Fixed Closing Fee-Amazon1"),
        ("marketplace","amazon","Listing Fee","Listing Fee-Amazon1"),
        ("marketplace","amazon","EasyShip Weight Handling Fee","EasyShip Weight Handling Fee-Amazon"),
        ("marketplace","amazon","Technology Fees","Technology Fees-Amazon1"),
        ("marketplace","amazon","Inbound Transportation Fee","Inbound Transportation Fee-Amazon1"),
        ("marketplace","amazon","Refund Processing Fee","Refund Processing Fee-Amazon1"),
        ("marketplace","amazon","Delivery Service Fee","DELIVERY SERIVE FEE"),
        ("marketplace","amazon","Shipping Fee","SHIPPING FEE-AMAZON"),

        ("marketplace","flipkart","Collection Fee","COLLECTION FEE-FLIPKART"),
        ("marketplace","flipkart","Pick And Pack Fee","Pick And Pack Fee-Flipkart"),
        ("marketplace","flipkart","Shipping Fee","SHIPPING FEE -FLIPKART"),
        ("marketplace","flipkart","Customer Add-ons Amount Recovery","CUSTMER ADD ONS AMOUNT RECOVERY -FLIPKART"),
        ("marketplace","flipkart","Customer Add-ons","CUSTMER ADD ONS AMOUNT RECOVERY -FLIPKART"),
        ("marketplace","flipkart","Fixed Fee","FIXED FEE-FLIPKART"),
        ("marketplace","flipkart","Commission Fee","COMMISSION FEE-FLIPKART"),
        ("marketplace","flipkart","Storage Fee","STORAGE FEE-FLIPKART"),

        ("marketplace","myntra","Commission","COMMSION -MYNTRA"),
        ("marketplace","myntra","Commission_","COMMSION -MYNTRA"),
        ("marketplace","myntra","Shipping_Charges","SHIPPING CHARGES-MYNTRA"),
        ("marketplace","myntra","Shipping Charges","SHIPPING CHARGES-MYNTRA"),
        ("marketplace","myntra","Fixed_Fees","FIXED FEE-MYNTRA"),
        ("marketplace","myntra","Fixed Fees","FIXED FEE-MYNTRA"),
        ("marketplace","myntra","Logistics","LOGISTICS FEE-MYNTRA"),


        ("marketplace","meesho_limited","Advertisement Fees","Advertisement Fees-Meesho"),
        ("marketplace","meesho_limited","Logistics charges","Logistics Charges-Meesho"),
        ("marketplace","meesho_limited","Other support-services charge","Other Support Services-Meesho"),
        ("marketplace","meesho_technologies","Advertisement Fees","Advertisement Fees-Meesho"),
        ("marketplace","meesho_technologies","Logistics charges","Logistics Charges-Meesho"),
        ("marketplace","meesho_technologies","Other support-services charge","Other Support Services-Meesho"),
        ("marketplace","valmo","Goods Transportation Charges","GOODS TRANSPORTATION CHARGES-VALMO"),
        ("marketplace","meesho","Advertisement Fees","Advertisement Fees-Meesho"),
        ("marketplace","flipkart","Ad Services Fee","AD SERVICES FEE-FLIPKART"),
        ("marketplace","amazon","Business Support Services","Business Support Services-Amazon"),
        ("marketplace","flipkart","Removal Fee","REMOVAL FEE-FLIPKART"),
        ("marketplace","meesho","Logistics charges","Logistics Charges-Meesho"),
        ("marketplace","meesho","Other support-services charge","Other Support Services-Meesho"),
    ]
    for tool, platform, pattern, ledger in mappings:
        q.execute("""INSERT OR IGNORE INTO ledger_mappings(company_name,tool,platform,pattern,voucher_type,ledger,match_type,enabled)
                     VALUES(?,?,?,?,?,?,?,1)""",
                  ("Default Company", tool, platform, pattern, "", ledger, "contains"))

    for platform in ["amazon", "flipkart", "meesho", "meesho_limited", "meesho_technologies", "valmo", "myntra"]:
        q.execute("INSERT OR IGNORE INTO voucher_rules(company_name,platform,pdf_doc_type,tally_voucher_type,sign_mode) VALUES(?,?,?,?,?)",
                  ("Default Company", platform, "Tax Invoice", "Purchase", "charge"))
        q.execute("INSERT OR IGNORE INTO voucher_rules(company_name,platform,pdf_doc_type,tally_voucher_type,sign_mode) VALUES(?,?,?,?,?)",
                  ("Default Company", platform, "Credit Note", "Debit Note", "reverse"))
    conn.commit()

def companies():
    init_db()
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM companies ORDER BY name")]

def company(name):
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM companies WHERE name=?", (name,)).fetchone()
        return dict(row) if row else {}

def df_table(table, company_name=None):
    init_db()
    with connect() as conn:
        if company_name and table in ["bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules"]:
            rows = conn.execute(f"SELECT * FROM {table} WHERE company_name=? ORDER BY id", (company_name,)).fetchall()
        else:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return pd.DataFrame([dict(r) for r in rows])

def save_company(row):
    init_db()
    with connect() as conn:
        conn.execute("""INSERT INTO companies(name,tally_company_name,gstin,state,suspense_ledger,cgst_ledger,sgst_ledger,igst_ledger)
                        VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(name) DO UPDATE SET
                        tally_company_name=excluded.tally_company_name,
                        gstin=excluded.gstin,
                        state=excluded.state,
                        suspense_ledger=excluded.suspense_ledger,
                        cgst_ledger=excluded.cgst_ledger,
                        sgst_ledger=excluded.sgst_ledger,
                        igst_ledger=excluded.igst_ledger""",
                     (row.get("name"), row.get("tally_company_name"), row.get("gstin"), row.get("state"),
                      row.get("suspense_ledger"), row.get("cgst_ledger"), row.get("sgst_ledger"), row.get("igst_ledger")))
        conn.commit()

def replace_table(table, company_name, rows):
    init_db()
    with connect() as conn:
        conn.execute(f"DELETE FROM {table} WHERE company_name=?", (company_name,))
        for r in rows:
            if table == "bank_accounts" and str(r.get("bank_ledger","")).strip():
                conn.execute("INSERT INTO bank_accounts(company_name,account_hint,bank_ledger,notes) VALUES(?,?,?,?)",
                             (company_name, r.get("account_hint",""), r.get("bank_ledger",""), r.get("notes","")))
            elif table == "party_ledgers" and str(norm_platform(r.get("platform",""))).strip():
                conn.execute("INSERT INTO party_ledgers(company_name,platform,party_ledger,party_gstin,state) VALUES(?,?,?,?,?)",
                             (company_name, norm_platform(r.get("platform","")), r.get("party_ledger",""), r.get("party_gstin",""), r.get("state","")))
            elif table == "ledger_mappings" and str(r.get("pattern","")).strip():
                conn.execute("""INSERT INTO ledger_mappings(company_name,tool,platform,pattern,voucher_type,ledger,match_type,enabled,notes)
                                VALUES(?,?,?,?,?,?,?,?,?)""",
                             (company_name, norm_platform(r.get("tool","")), norm_platform(r.get("platform","")), r.get("pattern",""),
                              r.get("voucher_type",""), r.get("ledger",""), r.get("match_type","contains"),
                              int(bool(r.get("enabled", True))), r.get("notes","")))
            elif table == "voucher_rules" and str(norm_platform(r.get("platform",""))).strip():
                conn.execute("INSERT INTO voucher_rules(company_name,platform,pdf_doc_type,tally_voucher_type,sign_mode) VALUES(?,?,?,?,?)",
                             (company_name, norm_platform(r.get("platform","")), r.get("pdf_doc_type",""),
                              r.get("tally_voucher_type",""), r.get("sign_mode","")))
        conn.commit()

def add_mapping(company_name, tool, platform, pattern, ledger, voucher_type=""):
    if not str(pattern).strip() or not str(ledger).strip():
        return
    init_db()
    c = norm_text(company_name)
    t = norm_platform(tool)
    p = norm_platform(platform)
    vt = norm_text(voucher_type)
    with connect() as conn:
        conn.execute("DELETE FROM ledger_mappings WHERE company_name=? AND tool=? AND platform=? AND pattern=? AND voucher_type=?",
                     (c, t, p, pattern, vt))
        conn.execute("""INSERT INTO ledger_mappings(company_name,tool,platform,pattern,voucher_type,ledger,match_type,enabled)
                        VALUES(?,?,?,?,?,?,?,1)""",
                     (c, t, p, pattern, vt, norm_text(ledger), "contains"))
        conn.commit()

def map_ledger(company_name, tool, platform, description, voucher_type=""):
    comp = company(company_name)
    suspense = comp.get("suspense_ledger", "Suspense")
    desc = str(description or "").lower()
    p = norm_platform(platform)
    t = norm_platform(tool)
    vt = norm_text(voucher_type).lower()

    def check_rows(rows):
        for rr in rows:
            r = dict(rr)
            rp = norm_platform(r.get("platform"))
            if rp and p and rp not in [p, "all"]:
                continue
            rvt = norm_text(r.get("voucher_type")).lower()
            if rvt and vt and rvt != vt:
                continue
            pat = str(r.get("pattern", "") or "")
            if pat and pat.lower() in desc:
                return norm_text(r.get("ledger")) or suspense, pat
        return None

    with connect() as conn:
        rows = conn.execute("""SELECT * FROM ledger_mappings
                               WHERE company_name=? AND LOWER(TRIM(tool))=? AND enabled=1
                               ORDER BY LENGTH(pattern) DESC""", (norm_text(company_name), t)).fetchall()
        found = check_rows(rows)
        if found:
            return found
        if norm_text(company_name) != "Default Company":
            rows = conn.execute("""SELECT * FROM ledger_mappings
                                   WHERE company_name='Default Company' AND LOWER(TRIM(tool))=? AND enabled=1
                                   ORDER BY LENGTH(pattern) DESC""", (t,)).fetchall()
            found = check_rows(rows)
            if found:
                return found
    return suspense, "UNMATCHED_TO_SUSPENSE"

def party_ledger(company_name, platform):
    init_db()
    p = norm_platform(platform)
    c = norm_text(company_name)

    def find_in_rows(rows, wanted):
        for rr in rows:
            r = dict(rr)
            if norm_platform(r.get("platform")) == wanted and norm_text(r.get("party_ledger")):
                return norm_text(r.get("party_ledger"))
        return ""

    with connect() as conn:
        rows = conn.execute("SELECT platform, party_ledger FROM party_ledgers WHERE company_name=?", (c,)).fetchall()
        val = find_in_rows(rows, p)
        if val:
            return val
        rows = conn.execute("SELECT platform, party_ledger FROM party_ledgers WHERE company_name='Default Company'").fetchall()
        val = find_in_rows(rows, p)
        if val:
            return val
        rows = conn.execute("SELECT platform, party_ledger FROM party_ledgers WHERE company_name=?", (c,)).fetchall()
        val = find_in_rows(rows, "unknown")
        if val:
            return val
        rows = conn.execute("SELECT platform, party_ledger FROM party_ledgers WHERE company_name='Default Company'").fetchall()
        val = find_in_rows(rows, "unknown")
        return val or "Suspense"

def voucher_rule(company_name, platform, pdf_doc_type):
    init_db()
    c = norm_text(company_name)
    p = norm_platform(platform)
    d = norm_text(pdf_doc_type)

    def find_rule(rows):
        for rr in rows:
            r = dict(rr)
            if norm_platform(r.get("platform")) == p and norm_text(r.get("pdf_doc_type")) == d:
                return r
        return None

    with connect() as conn:
        rows = conn.execute("SELECT * FROM voucher_rules WHERE company_name=?", (c,)).fetchall()
        row = find_rule(rows)
        if row:
            return row
        rows = conn.execute("SELECT * FROM voucher_rules WHERE company_name='Default Company'").fetchall()
        row = find_rule(rows)
        if row:
            return row
    if str(pdf_doc_type).lower() == "credit note":
        return {"tally_voucher_type": "Debit Note", "sign_mode": "reverse"}
    return {"tally_voucher_type": "Purchase", "sign_mode": "charge"}


# =========================
# ADVANCED DATABASE OVERRIDE
# =========================
_DB_READY = False

def init_db(force=False):
    """Fast, normalized, company-wise shared database initializer."""
    global _DB_READY
    if _DB_READY and not force:
        return
    conn = connect()
    q = conn.cursor()
    q.execute("""CREATE TABLE IF NOT EXISTS companies(
        name TEXT PRIMARY KEY,
        tally_company_name TEXT,
        gstin TEXT,
        state TEXT,
        suspense_ledger TEXT DEFAULT 'Suspense',
        cgst_ledger TEXT DEFAULT 'INPUT CGST',
        sgst_ledger TEXT DEFAULT 'INPUT SGST',
        igst_ledger TEXT DEFAULT 'INPUT IGST'
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS bank_accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        account_hint TEXT,
        bank_ledger TEXT,
        notes TEXT
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS party_ledgers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        platform TEXT,
        party_ledger TEXT,
        party_gstin TEXT,
        state TEXT
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS ledger_mappings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        tool TEXT,
        platform TEXT,
        pattern TEXT,
        voucher_type TEXT DEFAULT '',
        ledger TEXT,
        match_type TEXT DEFAULT 'contains',
        enabled INTEGER DEFAULT 1,
        notes TEXT
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS voucher_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        platform TEXT,
        pdf_doc_type TEXT,
        tally_voucher_type TEXT,
        sign_mode TEXT
    )""")
    q.execute("""CREATE TABLE IF NOT EXISTS import_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        tool TEXT,
        platform TEXT,
        invoice_no TEXT,
        voucher_type TEXT,
        voucher_date TEXT,
        amount REAL,
        source_file TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    seed_defaults(conn)
    normalize_existing_data(conn)
    _dedupe_and_index(conn)
    conn.close()
    _DB_READY = True

def reset_db_cache():
    global _DB_READY
    _DB_READY = False

def companies():
    init_db()
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM companies ORDER BY name")]

def company(name):
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM companies WHERE name=?", (norm_text(name),)).fetchone()
        return dict(row) if row else {}

def df_table(table, company_name=None):
    init_db()
    allowed = {"companies","bank_accounts","party_ledgers","ledger_mappings","voucher_rules","import_history"}
    if table not in allowed:
        raise ValueError("Invalid table")
    with connect() as conn:
        if company_name and table in ["bank_accounts", "party_ledgers", "ledger_mappings", "voucher_rules", "import_history"]:
            rows = conn.execute(f"SELECT * FROM {table} WHERE company_name=? ORDER BY id", (norm_text(company_name),)).fetchall()
        else:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return pd.DataFrame([dict(r) for r in rows])

def save_company(row):
    init_db()
    name = norm_text(row.get("name"))
    if not name:
        return
    with connect() as conn:
        conn.execute("""INSERT INTO companies(name,tally_company_name,gstin,state,suspense_ledger,cgst_ledger,sgst_ledger,igst_ledger)
                        VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(name) DO UPDATE SET
                        tally_company_name=excluded.tally_company_name,
                        gstin=excluded.gstin,
                        state=excluded.state,
                        suspense_ledger=excluded.suspense_ledger,
                        cgst_ledger=excluded.cgst_ledger,
                        sgst_ledger=excluded.sgst_ledger,
                        igst_ledger=excluded.igst_ledger""",
                     (name,
                      norm_text(row.get("tally_company_name")) or name,
                      norm_text(row.get("gstin")),
                      norm_text(row.get("state")),
                      norm_text(row.get("suspense_ledger")) or "Suspense",
                      norm_text(row.get("cgst_ledger")) or "INPUT CGST",
                      norm_text(row.get("sgst_ledger")) or "INPUT SGST",
                      norm_text(row.get("igst_ledger")) or "INPUT IGST"))
        conn.commit()
    reset_db_cache()

def delete_company(name):
    init_db()
    name = norm_text(name)
    if not name or name == "Default Company":
        return False
    with connect() as conn:
        for table in ["bank_accounts","party_ledgers","ledger_mappings","voucher_rules","import_history"]:
            conn.execute(f"DELETE FROM {table} WHERE company_name=?", (name,))
        conn.execute("DELETE FROM companies WHERE name=?", (name,))
        conn.commit()
    reset_db_cache()
    return True

def copy_company(source, target):
    init_db()
    source = norm_text(source)
    target = norm_text(target)
    if not source or not target:
        return False
    src = company(source)
    if not src:
        return False
    src["name"] = target
    src["tally_company_name"] = target
    save_company(src)
    with connect() as conn:
        for table, cols in {
            "bank_accounts": ["account_hint","bank_ledger","notes"],
            "party_ledgers": ["platform","party_ledger","party_gstin","state"],
            "ledger_mappings": ["tool","platform","pattern","voucher_type","ledger","match_type","enabled","notes"],
            "voucher_rules": ["platform","pdf_doc_type","tally_voucher_type","sign_mode"],
        }.items():
            rows = conn.execute(f"SELECT {','.join(cols)} FROM {table} WHERE company_name=?", (source,)).fetchall()
            conn.execute(f"DELETE FROM {table} WHERE company_name=?", (target,))
            for rr in rows:
                vals = [dict(rr).get(c) for c in cols]
                placeholders = ",".join(["?"] * (len(cols)+1))
                conn.execute(f"INSERT INTO {table}(company_name,{','.join(cols)}) VALUES({placeholders})", [target] + vals)
        conn.commit()
    reset_db_cache()
    return True

def replace_table(table, company_name, rows):
    init_db()
    company_name = norm_text(company_name)
    with connect() as conn:
        conn.execute(f"DELETE FROM {table} WHERE company_name=?", (company_name,))
        for r in rows:
            if table == "bank_accounts" and norm_text(r.get("bank_ledger")):
                conn.execute("INSERT INTO bank_accounts(company_name,account_hint,bank_ledger,notes) VALUES(?,?,?,?)",
                             (company_name, norm_text(r.get("account_hint")), norm_text(r.get("bank_ledger")), norm_text(r.get("notes"))))
            elif table == "party_ledgers" and norm_platform(r.get("platform")):
                conn.execute("INSERT INTO party_ledgers(company_name,platform,party_ledger,party_gstin,state) VALUES(?,?,?,?,?)",
                             (company_name, norm_platform(r.get("platform")), norm_text(r.get("party_ledger")), norm_text(r.get("party_gstin")), norm_text(r.get("state"))))
            elif table == "ledger_mappings" and norm_text(r.get("pattern")):
                conn.execute("""INSERT INTO ledger_mappings(company_name,tool,platform,pattern,voucher_type,ledger,match_type,enabled,notes)
                                VALUES(?,?,?,?,?,?,?,?,?)""",
                             (company_name, norm_platform(r.get("tool")), norm_platform(r.get("platform")),
                              norm_text(r.get("pattern")), norm_text(r.get("voucher_type")), norm_text(r.get("ledger")),
                              norm_text(r.get("match_type")) or "contains", int(bool(r.get("enabled", True))), norm_text(r.get("notes"))))
            elif table == "voucher_rules" and norm_platform(r.get("platform")):
                conn.execute("INSERT INTO voucher_rules(company_name,platform,pdf_doc_type,tally_voucher_type,sign_mode) VALUES(?,?,?,?,?)",
                             (company_name, norm_platform(r.get("platform")), norm_text(r.get("pdf_doc_type")),
                              norm_text(r.get("tally_voucher_type")), norm_text(r.get("sign_mode"))))
        normalize_existing_data(conn)
        _dedupe_and_index(conn)
        conn.commit()
    reset_db_cache()

def delete_rows(table, ids):
    init_db()
    allowed = {"bank_accounts","party_ledgers","ledger_mappings","voucher_rules","import_history"}
    if table not in allowed:
        return 0
    ids = [int(x) for x in ids if str(x).strip().isdigit()]
    if not ids:
        return 0
    with connect() as conn:
        q = ",".join(["?"] * len(ids))
        cur = conn.execute(f"DELETE FROM {table} WHERE id IN ({q})", ids)
        conn.commit()
    reset_db_cache()
    return cur.rowcount

def add_mapping(company_name, tool, platform, pattern, ledger, voucher_type=""):
    if not norm_text(pattern) or not norm_text(ledger):
        return
    init_db()
    c = norm_text(company_name)
    t = norm_platform(tool)
    p = norm_platform(platform)
    vt = norm_text(voucher_type)
    with connect() as conn:
        conn.execute("DELETE FROM ledger_mappings WHERE company_name=? AND tool=? AND platform=? AND pattern=? AND voucher_type=?",
                     (c, t, p, norm_text(pattern), vt))
        conn.execute("""INSERT INTO ledger_mappings(company_name,tool,platform,pattern,voucher_type,ledger,match_type,enabled)
                        VALUES(?,?,?,?,?,?,?,1)""",
                     (c, t, p, norm_text(pattern), vt, norm_text(ledger), "contains"))
        conn.commit()
    reset_db_cache()

def upsert_party_ledger(company_name, platform, party_ledger, party_gstin="", state=""):
    init_db()
    c = norm_text(company_name)
    p = norm_platform(platform)
    if not c or not p:
        return
    with connect() as conn:
        conn.execute("DELETE FROM party_ledgers WHERE company_name=? AND platform=?", (c, p))
        conn.execute("INSERT INTO party_ledgers(company_name,platform,party_ledger,party_gstin,state) VALUES(?,?,?,?,?)",
                     (c, p, norm_text(party_ledger), norm_text(party_gstin), norm_text(state)))
        conn.commit()
    reset_db_cache()

def map_ledger(company_name, tool, platform, description, voucher_type=""):
    init_db()
    comp = company(company_name)
    suspense = comp.get("suspense_ledger", "Suspense")
    desc = str(description or "").lower()
    p = norm_platform(platform)
    t = norm_platform(tool)
    vt = norm_text(voucher_type).lower()

    def check_rows(rows):
        for rr in rows:
            r = dict(rr)
            if not int(r.get("enabled", 1) or 0):
                continue
            rp = norm_platform(r.get("platform"))
            if rp and p and rp not in [p, "all"]:
                continue
            rvt = norm_text(r.get("voucher_type")).lower()
            if rvt and vt and rvt != vt:
                continue
            pat = norm_text(r.get("pattern"))
            if not pat:
                continue
            mt = norm_text(r.get("match_type")).lower() or "contains"
            p_low = pat.lower()
            ok = False
            if mt in ["contains", "smart_contains"]:
                ok = p_low in desc
            elif mt == "equals":
                ok = p_low == desc.strip()
            elif mt == "starts_with":
                ok = desc.strip().startswith(p_low)
            elif mt == "regex":
                try:
                    ok = re.search(pat, str(description or ""), flags=re.I) is not None
                except Exception:
                    ok = False
            if ok:
                return norm_text(r.get("ledger")) or suspense, pat
        return None

    with connect() as conn:
        rows = conn.execute("""SELECT * FROM ledger_mappings
                               WHERE company_name=? AND LOWER(TRIM(tool))=?
                               ORDER BY LENGTH(pattern) DESC""", (norm_text(company_name), t)).fetchall()
        found = check_rows(rows)
        if found:
            return found
        if norm_text(company_name) != "Default Company":
            rows = conn.execute("""SELECT * FROM ledger_mappings
                                   WHERE company_name='Default Company' AND LOWER(TRIM(tool))=?
                                   ORDER BY LENGTH(pattern) DESC""", (t,)).fetchall()
            found = check_rows(rows)
            if found:
                return found
    return suspense, "UNMATCHED_TO_SUSPENSE"

def party_ledger(company_name, platform):
    init_db()
    p = norm_platform(platform)
    c = norm_text(company_name)

    def find_in_rows(rows, wanted):
        for rr in rows:
            r = dict(rr)
            if norm_platform(r.get("platform")) == wanted and norm_text(r.get("party_ledger")):
                return norm_text(r.get("party_ledger"))
        return ""

    with connect() as conn:
        rows = conn.execute("SELECT platform, party_ledger FROM party_ledgers WHERE company_name=?", (c,)).fetchall()
        val = find_in_rows(rows, p)
        if val:
            return val
        rows = conn.execute("SELECT platform, party_ledger FROM party_ledgers WHERE company_name='Default Company'").fetchall()
        val = find_in_rows(rows, p)
        if val:
            return val
        rows = conn.execute("SELECT platform, party_ledger FROM party_ledgers WHERE company_name=?", (c,)).fetchall()
        val = find_in_rows(rows, "unknown")
        if val:
            return val
        rows = conn.execute("SELECT platform, party_ledger FROM party_ledgers WHERE company_name='Default Company'").fetchall()
        val = find_in_rows(rows, "unknown")
        return val or "Suspense"

def voucher_rule(company_name, platform, pdf_doc_type):
    init_db()
    c = norm_text(company_name)
    p = norm_platform(platform)
    d = norm_text(pdf_doc_type)

    def find_rule(rows):
        for rr in rows:
            r = dict(rr)
            if norm_platform(r.get("platform")) == p and norm_text(r.get("pdf_doc_type")) == d:
                return r
        return None

    with connect() as conn:
        rows = conn.execute("SELECT * FROM voucher_rules WHERE company_name=?", (c,)).fetchall()
        row = find_rule(rows)
        if row:
            return row
        rows = conn.execute("SELECT * FROM voucher_rules WHERE company_name='Default Company'").fetchall()
        row = find_rule(rows)
        if row:
            return row
    if str(pdf_doc_type).lower() == "credit note":
        return {"tally_voucher_type": "Debit Note", "sign_mode": "reverse"}
    return {"tally_voucher_type": "Purchase", "sign_mode": "charge"}

def database_summary(company_name=None):
    init_db()
    company_name = norm_text(company_name)
    with connect() as conn:
        if company_name:
            c = (company_name,)
            return {
                "companies": len(companies()),
                "bank_accounts": conn.execute("SELECT COUNT(*) FROM bank_accounts WHERE company_name=?", c).fetchone()[0],
                "party_ledgers": conn.execute("SELECT COUNT(*) FROM party_ledgers WHERE company_name=?", c).fetchone()[0],
                "ledger_mappings": conn.execute("SELECT COUNT(*) FROM ledger_mappings WHERE company_name=?", c).fetchone()[0],
                "voucher_rules": conn.execute("SELECT COUNT(*) FROM voucher_rules WHERE company_name=?", c).fetchone()[0],
                "unmapped_bank_rules": conn.execute("SELECT COUNT(*) FROM ledger_mappings WHERE company_name=? AND tool='bank' AND (ledger='' OR ledger='Suspense')", c).fetchone()[0],
                "unmapped_marketplace_rules": conn.execute("SELECT COUNT(*) FROM ledger_mappings WHERE company_name=? AND tool='marketplace' AND (ledger='' OR ledger='Suspense')", c).fetchone()[0],
            }
        return {
            "companies": conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "bank_accounts": conn.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0],
            "party_ledgers": conn.execute("SELECT COUNT(*) FROM party_ledgers").fetchone()[0],
            "ledger_mappings": conn.execute("SELECT COUNT(*) FROM ledger_mappings").fetchone()[0],
            "voucher_rules": conn.execute("SELECT COUNT(*) FROM voucher_rules").fetchone()[0],
        }

def cleanup_database():
    init_db(force=True)
    with connect() as conn:
        normalize_existing_data(conn)
        _dedupe_and_index(conn)
        conn.commit()
    reset_db_cache()
    init_db(force=True)

def backup_database(label="backup"):
    init_db()
    from datetime import datetime
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(label or "backup"))
    out = DATA_DIR / f"business_rules_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    import shutil
    shutil.copy2(DB_PATH, out)
    return out
