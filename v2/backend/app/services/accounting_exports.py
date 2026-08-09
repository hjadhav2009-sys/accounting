from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from ..document_intelligence.native_pdf import NativePdfExtractor
from ..document_intelligence.security import ResourceLimits
from .legacy import LegacyPdfToExcelService


EXCEL_COLUMNS=("DATE","INVOICE NO(Invoice Id).","GSTIN( from ship to )",
    "TRADE NAME( from Ship To Shiv Jagdamba,)","RATE","TAXABLE","HSN CODE","QTY",
    "Platform Name(Optional)","GSTIN of e-commerce operator ( from  shipped from )")


def _decimal(value:Any)->Decimal:
    try:return Decimal(str(value or 0).replace(",",""))
    except Exception:return Decimal("0")


def normalized_excel_rows(normalized:dict[str,Any],source_file:str)->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    invoice=normalized.get("invoice_number","");date=normalized.get("invoice_date") or ""
    supplier=normalized.get("supplier","");items=list(normalized.get("items") or []);buckets=list(normalized.get("tax_buckets") or [])
    rows=[]
    for bucket in buckets:
        rows.append({"DATE":date,"INVOICE NO(Invoice Id).":invoice,"GSTIN( from ship to )":"",
            "TRADE NAME( from Ship To Shiv Jagdamba,)":supplier,"RATE":str(bucket.get("rate") or "0"),
            "TAXABLE":str(bucket.get("taxable") or "0"),"HSN CODE":bucket.get("hsn_sac") or "",
            "QTY":str(sum((_decimal(item.get("quantity")) for item in items if not bucket.get("hsn_sac") or item.get("hsn_sac")==bucket.get("hsn_sac")),Decimal("0"))),
            "Platform Name(Optional)":"","GSTIN of e-commerce operator ( from  shipped from )":""})
    item_rows=[{"source_file":source_file,"invoice_id":invoice,"date":date,"description":item.get("description",''),
        "hsn":item.get("hsn_sac",''),"qty":item.get("quantity",0),"unit":item.get("unit",''),
        "unit_price":item.get("unit_rate",0),"taxable":item.get("taxable",0),"total":item.get("total",0)} for item in items]
    return rows,item_rows


def excel_preview(content:bytes,source_file:str,normalized:dict[str,Any])->dict[str,Any]:
    pages=NativePdfExtractor().extract(content,ResourceLimits())
    text="\n".join(page.text for page in pages);legacy=LegacyPdfToExcelService();template=legacy.detect_template(text)
    rows,item_rows=legacy.parse_text(template,text,source_file) if template!="unknown" else ([],[])
    if not rows:rows,item_rows=normalized_excel_rows(normalized,source_file)
    taxable=sum((_decimal(row.get("TAXABLE")) for row in rows),Decimal("0"))
    quantity=sum((_decimal(row.get("QTY")) for row in rows),Decimal("0"))
    total=sum((_decimal(item.get("total")) for item in item_rows),Decimal("0"))
    return {"template":template,"columns":list(EXCEL_COLUMNS),"rows":rows,"item_rows":item_rows,
        "summary":{"rows":len(rows),"quantity":str(quantity),"taxable":str(taxable),"total":str(total)}}


def safe_export_filename(source_file:str)->str:
    stem="".join(character if character.isalnum() or character in "-_" else "_" for character in Path(source_file).stem).strip("_")
    return f"{stem or 'accounting_export'}.xlsx"
