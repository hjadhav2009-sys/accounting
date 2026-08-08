from __future__ import annotations

from collections import defaultdict
from typing import Dict, List


def combine_rows(rows: List[Dict], force_18_hsn: str = "73269099", ignore_zero_taxable: bool = True) -> List[Dict]:
    grouped = defaultdict(lambda: {
        "DATE": "",
        "INVOICE NO(Invoice Id).": "",
        "GSTIN( from ship to )": "",
        "TRADE NAME( from Ship To Shiv Jagdamba,)": "",
        "RATE": "",
        "TAXABLE": 0.0,
        "HSN CODE": "",
        "QTY": 0.0,
        "Platform Name(Optional)": "",
        "GSTIN of e-commerce operator ( from  shipped from )": "",
    })

    for row in rows:
        taxable = float(row.get("TAXABLE") or 0)
        qty = float(row.get("QTY") or 0)
        if ignore_zero_taxable and abs(taxable) < 0.000001:
            continue

        rate = str(row.get("RATE", "")).replace("%", "").strip()
        hsn = str(row.get("HSN CODE", "")).strip()
        if rate in {"18", "18.0"} and force_18_hsn:
            hsn = force_18_hsn
            rate = "18"
        if rate in {"3.0"}:
            rate = "3"
        if rate in {"5.0"}:
            rate = "5"

        key = (
            row.get("DATE", ""),
            row.get("INVOICE NO(Invoice Id).", ""),
            row.get("GSTIN( from ship to )", ""),
            row.get("TRADE NAME( from Ship To Shiv Jagdamba,)", ""),
            rate,
            hsn,
            row.get("Platform Name(Optional)", ""),
            row.get("GSTIN of e-commerce operator ( from  shipped from )", ""),
        )
        g = grouped[key]
        g["DATE"] = key[0]
        g["INVOICE NO(Invoice Id)."] = key[1]
        g["GSTIN( from ship to )"] = key[2]
        g["TRADE NAME( from Ship To Shiv Jagdamba,)"] = key[3]
        g["RATE"] = key[4]
        g["HSN CODE"] = key[5]
        g["Platform Name(Optional)"] = key[6]
        g["GSTIN of e-commerce operator ( from  shipped from )"] = key[7]
        g["TAXABLE"] += taxable
        g["QTY"] += qty

    out = list(grouped.values())
    for row in out:
        row["TAXABLE"] = round(row["TAXABLE"], 2)
        row["QTY"] = round(row["QTY"], 2)
    return out
