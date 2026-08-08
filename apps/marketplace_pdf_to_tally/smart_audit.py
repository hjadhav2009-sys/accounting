
from pathlib import Path
import re
import pandas as pd

from apps.marketplace_pdf_to_tally.engine import (
    read_pdf_text, detect_platform, detect_doc_type, invoice_no, invoice_date,
    is_hsn, lines, amount
)

def _estimate_amazon_rows(text):
    summary = re.split(r"Details of Fees to the above", text, flags=re.I)[0]
    ls = lines(summary)
    count = 0
    for i, line in enumerate(ls):
        if not is_hsn(line):
            continue
        window = " ".join(ls[i:i+14])
        if re.search(r"-?\s*(?:INR|Rs)?\s*[\d,]+\.\d{2}", window, re.I):
            count += 1
    return count

def _estimate_generic_hsn_rows(text):
    ls = lines(text)
    count = 0
    for i, line in enumerate(ls):
        if not is_hsn(line):
            continue
        window = " ".join(ls[i:i+12])
        if re.search(r"\d+(?:,\d{3})*\.\d{2}", window):
            count += 1
    return count

def estimate_expected_rows(text, platform):
    # This is only a safety estimate. It must not create false export-blocking warnings.
    if platform == "amazon":
        return _estimate_amazon_rows(text)
    if platform in ["flipkart", "myntra"]:
        return _estimate_generic_hsn_rows(text)
    # Meesho PDFs can include extra HSN/tax summary structures, so avoid hard row estimate.
    return 0

def _find_pdf_total_hint(text):
    """Best-effort total hint. Informational only, not a hard failure."""
    patterns = [
        r"Total Invoice Amount\s*[:\-]?\s*-?\s*(?:INR|Rs\.?|₹)?\s*([\d,]+\.\d{2})",
        r"Total Amount\s*[:\-]?\s*-?\s*(?:INR|Rs\.?|₹)?\s*([\d,]+\.\d{2})",
        r"Grand Total\s*[:\-]?\s*-?\s*(?:INR|Rs\.?|₹)?\s*([\d,]+\.\d{2})",
    ]
    blob = re.sub(r"\s+", " ", text)
    vals = []
    for pat in patterns:
        for m in re.finditer(pat, blob, flags=re.I):
            vals.append(amount(m.group(1)))
    return max(vals) if vals else 0.0

def audit_files(pdf_paths, parsed_df):
    parsed_df = parsed_df.copy() if parsed_df is not None else pd.DataFrame()
    rows = []
    for p in pdf_paths:
        path = Path(p)
        try:
            text = read_pdf_text(str(path))
            platform = detect_platform(text, path.name)
            doc_type = detect_doc_type(text)
            inv_no = invoice_no(text, str(path), path.name)
            inv_date = invoice_date(text)
            expected_rows = estimate_expected_rows(text, platform)
            pdf_total_hint = _find_pdf_total_hint(text)
        except Exception as e:
            rows.append({
                "Source PDF": path.name, "Platform": "unknown", "PDF Doc Type": "",
                "Invoice No": "", "Date": "", "Expected Rows": 0, "Parsed Rows": 0,
                "Parsed Total": 0.0, "PDF Total Hint": 0.0, "Result": "REVIEW",
                "Issue": f"PDF text read/audit failed: {e}", "Info": ""
            })
            continue

        part = parsed_df[parsed_df.get("Source PDF", "") == path.name] if not parsed_df.empty else pd.DataFrame()
        parsed_rows = len(part)
        parsed_total = float(part.get("Total", pd.Series(dtype=float)).sum()) if not part.empty else 0.0
        review_count = int((~part.get("Status", pd.Series(dtype=str)).astype(str).str.startswith("OK")).sum()) if not part.empty else 0

        hard_issues = []
        info = []

        if parsed_rows == 0:
            hard_issues.append("no parsed rows")
        if review_count:
            hard_issues.append(f"{review_count} review row(s)")

        # Only warn if estimated expected rows is clearly MORE than parsed rows.
        # Do not warn when parser splits more rows than the rough estimator.
        if expected_rows and parsed_rows and expected_rows > parsed_rows:
            hard_issues.append(f"row count mismatch: expected {expected_rows}, parsed {parsed_rows}")

        # Total hints are informational only. Some platforms show subtotal/net/credit signs differently.
        if pdf_total_hint and parsed_total and abs(pdf_total_hint - parsed_total) > 1.0:
            info.append(f"total hint differs: PDF hint {pdf_total_hint:.2f}, parsed {parsed_total:.2f}")

        result = "SAFE" if not hard_issues else "REVIEW"
        rows.append({
            "Source PDF": path.name,
            "Platform": platform,
            "PDF Doc Type": doc_type,
            "Invoice No": inv_no,
            "Date": inv_date,
            "Expected Rows": expected_rows,
            "Parsed Rows": parsed_rows,
            "Parsed Total": round(parsed_total, 2),
            "PDF Total Hint": round(pdf_total_hint, 2),
            "Result": result,
            "Issue": "; ".join(hard_issues),
            "Info": "; ".join(info),
        })
    return pd.DataFrame(rows)

def audit_rows(parsed_df):
    if parsed_df is None or parsed_df.empty:
        return pd.DataFrame(columns=["Source PDF", "Description", "Issue"])
    df = parsed_df.copy()
    problems = []

    for idx, r in df.iterrows():
        issues = []
        status = str(r.get("Status", ""))
        if not status.startswith("OK"):
            issues.append(status)
        if str(r.get("Mapped Ledger", "")).strip().lower() == "suspense":
            issues.append("mapped to Suspense")
        taxable = float(r.get("Taxable") or 0)
        total = float(r.get("Total") or 0)
        cgst = float(r.get("CGST") or 0)
        sgst = float(r.get("SGST") or 0)
        igst = float(r.get("IGST") or 0)
        if taxable == 0 and total == 0:
            issues.append("zero amount row")
        if total and abs((taxable + cgst + sgst + igst) - total) > 1.0:
            issues.append("row total mismatch")
        if issues:
            problems.append({
                "Row": idx,
                "Source PDF": r.get("Source PDF", ""),
                "Platform": r.get("Platform", ""),
                "PDF Doc Type": r.get("PDF Doc Type", ""),
                "Description": r.get("Description", ""),
                "Mapped Ledger": r.get("Mapped Ledger", ""),
                "Taxable": taxable,
                "CGST": cgst,
                "SGST": sgst,
                "IGST": igst,
                "Total": total,
                "Issue": "; ".join(issues),
            })
    return pd.DataFrame(problems)

def summary_message(file_audit_df, row_audit_df):
    if file_audit_df is None or file_audit_df.empty:
        return "No audit data yet."
    total_files = len(file_audit_df)
    review_files = int((file_audit_df["Result"] != "SAFE").sum())
    row_problems = 0 if row_audit_df is None else len(row_audit_df)
    if review_files == 0 and row_problems == 0:
        return f"SAFE TO EXPORT: {total_files} PDF(s) audited, no blocking issues found."
    return f"REVIEW NEEDED: {review_files}/{total_files} PDF(s) need review and {row_problems} row-level issue(s) were found."
