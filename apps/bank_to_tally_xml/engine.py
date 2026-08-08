
from pathlib import Path
import re
import pandas as pd
from datetime import datetime
from xml.sax.saxutils import escape
from difflib import SequenceMatcher

def clean_desc(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\n", " ").replace("￾", "-")).strip()

def clean_amount(v):
    if v is None:
        return ""
    s = str(v).strip().replace(",", "")
    if s in ["", "None", "nan"]:
        return ""
    try:
        return float(s)
    except Exception:
        return ""

def group_pattern_from_description(desc):
    s = clean_desc(desc)
    s = re.sub(r"^NEFT-[A-Z0-9]+-\s*", "", s, flags=re.I)
    s = re.sub(r"^UPI/\d+/", "", s, flags=re.I)
    m = re.match(r"^IMPS/\d+/([^/]+)", s, flags=re.I)
    if m:
        s = m.group(1)
    return re.sub(r"\s+", " ", s.strip(" -/")).strip()

def split_date_time(s):
    s = str(s or "").strip()
    m = re.match(r"(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}:\d{2}))?", s)
    if m:
        return m.group(1), (m.group(2) or "")
    return s, ""

def parse_pdf_tables(path):
    import pdfplumber
    rows = []
    account_text = ""
    with pdfplumber.open(str(path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            account_text += "\n" + (page.extract_text() or "")
            tables = page.extract_tables() or []
            for table in tables:
                if not table:
                    continue
                for row in table:
                    if not row or len(row) < 7:
                        continue
                    joined = " ".join(str(c or "") for c in row)
                    if "S.No" in joined and "Txn Date" in joined:
                        continue
                    sno = str(row[0] or "").strip()
                    if not sno.isdigit():
                        continue
                    txn_date, txn_time = split_date_time(row[1])
                    value_date = str(row[2] or "").strip()
                    desc = clean_desc(row[3])
                    withdrawal = clean_amount(row[5] if len(row) > 5 else "")
                    deposit = clean_amount(row[6] if len(row) > 6 else "")
                    balance = clean_amount(row[7] if len(row) > 7 else "")
                    rows.append({
                        "S.No": int(sno), "Page": page_no, "Txn Date": txn_date, "Txn Time": txn_time,
                        "Value Date": value_date, "Description": desc,
                        "Group Pattern": group_pattern_from_description(desc),
                        "Withdrawal": withdrawal, "Deposit": deposit, "Balance": balance
                    })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["S.No","Txn Date","Description","Withdrawal","Deposit"]).sort_values("S.No").reset_index(drop=True)
    return df, account_text

def load_statement(path):
    p = Path(path)
    ext = p.suffix.lower()
    account_text = ""
    if ext == ".pdf":
        return parse_pdf_tables(p)
    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(p)
    elif ext == ".csv":
        df = pd.read_csv(p)
    else:
        raise ValueError("Unsupported file type.")
    if "Description" in df.columns and "Group Pattern" not in df.columns:
        df["Group Pattern"] = df["Description"].apply(group_pattern_from_description)
    return df, account_text

def make_pattern_suggestions(df):
    if df.empty:
        return pd.DataFrame(columns=["enabled","Type","match_type","narration_pattern","sample_count","total_deposit","total_withdrawal","ledger"])
    tmp = df.copy()
    if "Group Pattern" not in tmp.columns:
        tmp["Group Pattern"] = tmp["Description"].apply(group_pattern_from_description)
    tmp["Deposit"] = pd.to_numeric(tmp.get("Deposit", 0), errors="coerce").fillna(0)
    tmp["Withdrawal"] = pd.to_numeric(tmp.get("Withdrawal", 0), errors="coerce").fillna(0)
    tmp["Type"] = tmp.apply(lambda r: "Receipt" if r["Deposit"] > 0 else ("Payment" if r["Withdrawal"] > 0 else ""), axis=1)
    out = tmp.groupby(["Type","Group Pattern"], dropna=False).agg(
        sample_count=("Description","count"),
        total_deposit=("Deposit","sum"),
        total_withdrawal=("Withdrawal","sum")
    ).reset_index().rename(columns={"Group Pattern":"narration_pattern"})
    out["enabled"] = True
    out["match_type"] = "contains"
    out["ledger"] = ""
    return out[["enabled","Type","match_type","narration_pattern","sample_count","total_deposit","total_withdrawal","ledger"]]

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

def smart_contains(narration, pattern):
    n = norm(narration); p = norm(pattern)
    if p in n:
        return True
    n_words = [w for w in n.split() if len(w) >= 3]
    p_words = [w for w in p.split() if len(w) >= 3]
    for pw in p_words:
        if pw in n:
            return True
        for nw in n_words:
            if len(pw) >= 5 and len(nw) >= 5 and SequenceMatcher(None, pw, nw).ratio() >= 0.78:
                return True
    return False

def map_ledger(narration, rules_payload):
    settings = rules_payload.get("settings", {})
    suspense = settings.get("unmatched_ledger", "Suspense")
    narration = str(narration or "")
    for r in rules_payload.get("rules", []):
        if not r.get("enabled", True):
            continue
        pat = str(r.get("narration_pattern", "") or "")
        if not pat:
            continue
        mt = r.get("match_type", "contains")
        if mt == "regex":
            try:
                matched = bool(re.search(pat, narration, re.I))
            except re.error:
                matched = False
        elif mt == "smart_contains":
            matched = smart_contains(narration, pat)
        else:
            matched = pat.lower() in narration.lower()
        if matched:
            return (str(r.get("ledger","") or "").strip() or suspense), pat
    if settings.get("unmatched_mode", "Suspense") == "Suspense":
        return suspense, "UNMATCHED_TO_SUSPENSE"
    return "", ""

def auto_bank_ledger(account_text, rules_payload):
    for row in rules_payload.get("bank_accounts", []):
        hint = str(row.get("account_hint","")).strip()
        if hint and hint in account_text:
            return row.get("bank_ledger","")
    return rules_payload.get("settings", {}).get("bank_ledger", "IDBI BANK -CURRENT")

def to_float(v):
    if v is None or pd.isna(v) or str(v).strip() == "":
        return 0.0
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0.0

def tally_date(v):
    s = str(v or "").strip()
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y%m%d")
        except Exception:
            pass
    d = re.sub(r"\D", "", s)
    return d if len(d) == 8 else s

def ledger_master(name, parent):
    n = escape(str(name)); p = escape(str(parent))
    return f"""
<TALLYMESSAGE xmlns:UDF="TallyUDF">
  <LEDGER NAME="{n}" ACTION="Create">
    <NAME>{n}</NAME><PARENT>{p}</PARENT>
    <ISBILLWISEON>No</ISBILLWISEON><ISCOSTCENTRESON>No</ISCOSTCENTRESON>
    <AFFECTSSTOCK>No</AFFECTSSTOCK><ISGSTAPPLICABLE>No</ISGSTAPPLICABLE>
    <LANGUAGENAME.LIST><NAME.LIST TYPE="String"><NAME>{n}</NAME></NAME.LIST><LANGUAGEID>1033</LANGUAGEID></LANGUAGENAME.LIST>
  </LEDGER>
</TALLYMESSAGE>"""

def voucher_xml(row, bank_ledger, voucher_no):
    desc = str(row.get("Description","") or "")
    ledger = str(row.get("Mapped Ledger","") or "").strip() or "Suspense"
    date = tally_date(row.get("Txn Date") or row.get("Value Date"))
    withdrawal = to_float(row.get("Withdrawal",0)); deposit = to_float(row.get("Deposit",0))
    if deposit > 0:
        vtype = "Receipt"; other_amt = deposit; bank_amt = -deposit
    elif withdrawal > 0:
        vtype = "Payment"; other_amt = -withdrawal; bank_amt = withdrawal
    else:
        return ""
    de = escape(desc); le = escape(ledger); be = escape(bank_ledger); vno = escape(str(voucher_no))
    return f"""
<TALLYMESSAGE xmlns:UDF="TallyUDF">
  <VOUCHER VCHTYPE="{vtype}" ACTION="Create" OBJVIEW="Accounting Voucher View">
    <DATE>{date}</DATE><VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME><VOUCHERNUMBER>{vno}</VOUCHERNUMBER>
    <NARRATION>{de}</NARRATION><PARTYLEDGERNAME>{be}</PARTYLEDGERNAME>
    <PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW><EFFECTIVEDATE>{date}</EFFECTIVEDATE><ISINVOICE>No</ISINVOICE>
    <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>{le}</LEDGERNAME><ISDEEMEDPOSITIVE>{"Yes" if other_amt < 0 else "No"}</ISDEEMEDPOSITIVE>
      <ISPARTYLEDGER>No</ISPARTYLEDGER><AMOUNT>{other_amt:.2f}</AMOUNT>
    </ALLLEDGERENTRIES.LIST>
    <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>{be}</LEDGERNAME><ISDEEMEDPOSITIVE>{"Yes" if bank_amt < 0 else "No"}</ISDEEMEDPOSITIVE>
      <ISPARTYLEDGER>Yes</ISPARTYLEDGER><AMOUNT>{bank_amt:.2f}</AMOUNT>
      <BANKALLOCATIONS.LIST><DATE>{date}</DATE><INSTRUMENTDATE>{date}</INSTRUMENTDATE><TRANSACTIONTYPE>Cheque</TRANSACTIONTYPE><PAYMENTMODE>Transacted</PAYMENTMODE><BANKPARTYNAME>{le}</BANKPARTYNAME><AMOUNT>{bank_amt:.2f}</AMOUNT></BANKALLOCATIONS.LIST>
    </ALLLEDGERENTRIES.LIST>
  </VOUCHER>
</TALLYMESSAGE>"""

def build_xml(df, settings):
    bank = settings.get("bank_ledger", "IDBI BANK -CURRENT")
    prefix = settings.get("voucher_number_prefix", "BANK-")
    suspense = settings.get("unmatched_ledger", "Suspense")
    sales_parent = settings.get("default_sales_parent", "Sales Accounts")
    expense_parent = settings.get("default_expense_parent", "Direct Expenses")
    suspense_parent = settings.get("default_suspense_parent", "Suspense A/c")
    messages = []

    # Important: OFF by default. Keep OFF if ledgers already exist in Tally.
    if settings.get("create_missing_ledgers", False):
        ledgers = sorted(set(str(x).strip() for x in df.get("Mapped Ledger", pd.Series()).fillna("") if str(x).strip()))
        for l in ledgers:
            if l == bank:
                continue
            parent = suspense_parent if l == suspense else (sales_parent if "Selling Through" in l else expense_parent)
            messages.append(ledger_master(l, parent))

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        msg = voucher_xml(row, bank, f"{prefix}{i:04d}" if prefix else "")
        if msg:
            messages.append(msg)
    return f"""<ENVELOPE>
  <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
  <BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC><REQUESTDATA>
  {''.join(messages)}
  </REQUESTDATA></IMPORTDATA></BODY>
</ENVELOPE>"""
