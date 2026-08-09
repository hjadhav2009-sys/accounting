from __future__ import annotations

import hashlib
import json
import re
import tempfile
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import UUID,uuid4
from xml.sax.saxutils import escape

from .legacy import LegacyMarketplaceService,LegacyBankStatementService


def _money(value:Any)->Decimal:
    try:return Decimal(str(value or 0).replace(",","")).quantize(Decimal("0.01"),ROUND_HALF_UP)
    except Exception:return Decimal("0.00")


def _match(text:str,pattern:str,match_type:str)->bool:
    left=text.casefold();right=pattern.casefold()
    if not right:return False
    if match_type=="equals":return left==right
    if match_type=="starts_with":return left.startswith(right)
    if match_type=="regex":
        try:return bool(re.search(pattern,text,re.I))
        except re.error:return False
    if match_type=="smart_contains":
        normalized=lambda value:" ".join(re.sub(r"[^a-z0-9]+"," ",value.casefold()).split())
        return normalized(pattern) in normalized(text)
    return right in left


class AccountingWorkflowRepository:
    def __init__(self,connect):self.connect=connect

    @staticmethod
    def _records(cursor):
        names=[column.name if hasattr(column,"name") else column[0] for column in cursor.description]
        return [dict(zip(names,row)) for row in cursor.fetchall()]

    def company_profile(self,organization_id:UUID,company_id:UUID)->dict[str,Any]|None:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,name,tally_company_name,gstin,state FROM companies WHERE id=%s AND organization_id=%s",(company_id,organization_id));row=cursor.fetchone()
                if not row:return None
                result={"id":row[0],"name":row[1],"tally_company_name":row[2],"gstin":row[3] or "","state":row[4] or ""}
                cursor.execute("SELECT platform,party_ledger FROM party_ledgers WHERE organization_id=%s AND company_id=%s",(organization_id,company_id));result["parties"]={str(item[0]).casefold():item[1] for item in cursor.fetchall()}
                cursor.execute("SELECT tax_type,ledger_name FROM gst_ledgers WHERE organization_id=%s AND company_id=%s",(organization_id,company_id));result["gst_ledgers"]={item[0]:item[1] for item in cursor.fetchall()}
                return result
        finally:connection.close()

    def mappings(self,organization_id:UUID,company_id:UUID,tool:str,platform:str="",voucher_type:str="")->list[dict[str,Any]]:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT id,platform,pattern,voucher_type,ledger,match_type,priority FROM ledger_mappings
                    WHERE organization_id=%s AND company_id=%s AND tool=%s AND enabled=true
                      AND (platform='' OR lower(platform)=lower(%s)) AND (voucher_type='' OR lower(voucher_type)=lower(%s))
                    ORDER BY priority DESC,length(pattern) DESC,id""",(organization_id,company_id,tool,platform,voucher_type))
                return self._records(cursor)
        finally:connection.close()

    def voucher_rule(self,organization_id:UUID,company_id:UUID,platform:str,document_type:str)->dict[str,Any]:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT tally_voucher_type,sign_mode FROM voucher_rules WHERE organization_id=%s AND company_id=%s
                    AND lower(platform)=lower(%s) AND lower(document_type)=lower(%s)""",(organization_id,company_id,platform,document_type));row=cursor.fetchone()
                if row:return {"tally_voucher_type":row[0],"sign_mode":row[1]}
                return {"tally_voucher_type":"Debit Note" if document_type.casefold()=="credit note" else "Purchase",
                        "sign_mode":"reverse" if document_type.casefold()=="credit note" else "charge"}
        finally:connection.close()

    def bank_accounts(self,organization_id:UUID,company_id:UUID)->list[dict[str,Any]]:
        connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT id,account_hint_token,bank_ledger,status FROM bank_accounts
                    WHERE organization_id=%s AND company_id=%s AND status='ACTIVE' ORDER BY bank_ledger,id""",(organization_id,company_id))
                return self._records(cursor)
        finally:connection.close()

    def save_mapping(self,organization_id:UUID,company_id:UUID,actor_id:UUID,tool:str,platform:str,pattern:str,
                     voucher_type:str,ledger:str,match_type:str)->UUID:
        if not pattern.strip() or not ledger.strip():raise ValueError("pattern and ledger are required")
        mapping_id=uuid4();connection=self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO ledger_mappings(id,organization_id,company_id,tool,platform,pattern,
                    voucher_type,ledger,match_type,priority,enabled) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,0,true)
                    ON CONFLICT(company_id,tool,platform,pattern,voucher_type) DO UPDATE SET ledger=excluded.ledger,
                    match_type=excluded.match_type,enabled=true RETURNING id""",
                    (mapping_id,organization_id,company_id,tool,platform.strip(),pattern.strip(),voucher_type.strip(),ledger.strip(),match_type))
                mapping_id=cursor.fetchone()[0]
                cursor.execute("""INSERT INTO audit_logs(id,organization_id,company_id,actor_id,action,entity_type,
                    entity_id,new_reference,reason,source_context) VALUES(%s,%s,%s,%s,'MAPPING_CHANGED','ledger_mapping',
                    %s,%s,'authorized V2 mapping update',%s::jsonb)""",(uuid4(),organization_id,company_id,actor_id,
                    str(mapping_id),hashlib.sha256(ledger.strip().encode()).hexdigest(),json.dumps({"tool":tool,"platform":platform,"pattern":pattern,"match_type":match_type})))
            connection.commit();return mapping_id
        except Exception:connection.rollback();raise
        finally:connection.close()


def marketplace_preview(content:bytes,filename:str,organization_id:UUID,company_id:UUID,repository:AccountingWorkflowRepository)->dict[str,Any]:
    profile=repository.company_profile(organization_id,company_id)
    if not profile:raise ValueError("company is not available")
    with tempfile.TemporaryDirectory(prefix="bap-marketplace-") as directory:
        path=Path(directory)/"source.pdf";path.write_bytes(content)
        frame=LegacyMarketplaceService().parse_pdf(path,profile["name"],filename)
    rows=[]
    for raw in frame.to_dict(orient="records"):
        row={key:("" if str(value)=="nan" else value) for key,value in raw.items()}
        platform=str(row.get("Platform") or "");document_type=str(row.get("PDF Doc Type") or "Tax Invoice")
        rule=repository.voucher_rule(organization_id,company_id,platform,document_type);row["Tally Voucher Type"]=rule["tally_voucher_type"]
        mappings=repository.mappings(organization_id,company_id,"marketplace",platform,document_type)
        matched=next((mapping for mapping in mappings if _match(str(row.get("Description") or ""),mapping["pattern"],mapping["match_type"])),None)
        row["Mapped Ledger"]=matched["ledger"] if matched else "Suspense";row["Matched By"]=matched["pattern"] if matched else "UNMATCHED_TO_SUSPENSE"
        party=profile["parties"].get(platform.casefold(),"");issues=[]
        if not matched:issues.append("UNKNOWN_LEDGER")
        if not party or party.casefold()=="suspense":issues.append("PARTY_LEDGER_REQUIRED")
        if str(row.get("Issue") or ""):issues.append(str(row["Issue"]))
        row["Status"]="OK" if not issues and bool(row.get("Import?",True)) else "REVIEW";row["Issue"]="; ".join(issues)
        row["Party Ledger"]=party;row["Sign Mode"]=rule["sign_mode"]
        for key in ("Taxable","CGST","SGST","IGST","Total"):row[key]=str(_money(row.get(key)))
        rows.append(row)
    mapping_snapshot=hashlib.sha256(json.dumps([{key:row.get(key) for key in ("Platform","PDF Doc Type","Description","Mapped Ledger","Matched By","Tally Voucher Type")} for row in rows],sort_keys=True).encode()).hexdigest()
    totals={key:str(sum((_money(row.get(key)) for row in rows),Decimal("0"))) for key in ("Taxable","CGST","SGST","IGST","Total")}
    return {"rows":rows,"totals":totals,"validation_status":"VERIFIED" if rows and all(row["Status"]=="OK" for row in rows) else "REVIEW",
        "mapping_snapshot_sha256":mapping_snapshot,"export_allowed":bool(rows and all(row["Status"]=="OK" for row in rows)),"profile":profile}


def _ledger_xml(ledger:str,amount:Decimal,party:bool=False)->str:
    return f"<LEDGERENTRIES.LIST><LEDGERNAME>{escape(ledger)}</LEDGERNAME><ISDEEMEDPOSITIVE>{'Yes' if amount<0 else 'No'}</ISDEEMEDPOSITIVE><ISPARTYLEDGER>{'Yes' if party else 'No'}</ISPARTYLEDGER><AMOUNT>{amount:.2f}</AMOUNT></LEDGERENTRIES.LIST>"


def marketplace_xml(preview:dict[str,Any])->bytes:
    if not preview["export_allowed"]:raise ValueError("marketplace XML is blocked until every mapping is verified")
    profile=preview["profile"];messages=[]
    grouped:dict[tuple,list[dict[str,Any]]]={}
    for row in preview["rows"]:grouped.setdefault(tuple(str(row.get(key) or "") for key in ("Source PDF","Platform","PDF Doc Type","Tally Voucher Type","Invoice No","Date")),[]).append(row)
    for (source,platform,document_type,voucher_type,invoice,date),rows in grouped.items():
        reverse=str(rows[0].get("Sign Mode"))=="reverse" or voucher_type.casefold()=="debit note";party=str(rows[0]["Party Ledger"])
        taxable=sum((_money(row["Taxable"]) for row in rows),Decimal("0"));cgst=sum((_money(row["CGST"]) for row in rows),Decimal("0"));sgst=sum((_money(row["SGST"]) for row in rows),Decimal("0"));igst=sum((_money(row["IGST"]) for row in rows),Decimal("0"));total=taxable+cgst+sgst+igst
        entries=[_ledger_xml(party,-total if reverse else total,True)]
        ledgers={}
        for row in rows:ledgers[row["Mapped Ledger"]]=ledgers.get(row["Mapped Ledger"],Decimal("0"))+_money(row["Taxable"])
        entries.extend(_ledger_xml(str(ledger),(Decimal("1") if reverse else Decimal("-1"))*amount) for ledger,amount in ledgers.items())
        for kind,amount in (("CGST",cgst),("SGST",sgst),("IGST",igst)):
            if amount:
                ledger=profile["gst_ledgers"].get(kind)
                if not ledger:raise ValueError(f"{kind} ledger is not configured")
                entries.append(_ledger_xml(ledger,(Decimal("1") if reverse else Decimal("-1"))*amount))
        messages.append(f"<TALLYMESSAGE xmlns:UDF=\"TallyUDF\"><VOUCHER VCHTYPE=\"{escape(voucher_type)}\" ACTION=\"Create\" OBJVIEW=\"Invoice Voucher View\"><DATE>{escape(date)}</DATE><VOUCHERTYPENAME>{escape(voucher_type)}</VOUCHERTYPENAME><PARTYLEDGERNAME>{escape(party)}</PARTYLEDGERNAME><VOUCHERNUMBER>{escape(invoice)}</VOUCHERNUMBER><REFERENCE>{escape(invoice)}</REFERENCE><PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW><ISINVOICE>Yes</ISINVOICE><NARRATION>{escape(platform.upper()+' '+document_type+' '+invoice+' '+source)}</NARRATION>{''.join(entries)}</VOUCHER></TALLYMESSAGE>")
    xml=f"<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>{escape(profile['tally_company_name'])}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA>{''.join(messages)}</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"
    return xml.encode("utf-8")


def reconcile_bank_rows(rows:list[dict[str,Any]],tolerance:Decimal=Decimal("0.01"))->dict[str,Any]:
    if not rows:return {"opening":"0.00","credits":"0.00","debits":"0.00","calculated_closing":"0.00","statement_closing":"0.00","difference":"0.00","status":"REVIEW"}
    credits=sum((_money(row.get("Deposit")) for row in rows),Decimal("0"));debits=sum((_money(row.get("Withdrawal")) for row in rows),Decimal("0"))
    first=rows[0];opening=_money(first.get("Balance"))-_money(first.get("Deposit"))+_money(first.get("Withdrawal"))
    statement=_money(rows[-1].get("Balance"));calculated=(opening+credits-debits).quantize(Decimal("0.01"));difference=(calculated-statement).quantize(Decimal("0.01"))
    return {"opening":str(opening),"credits":str(credits),"debits":str(debits),"calculated_closing":str(calculated),
        "statement_closing":str(statement),"difference":str(difference),"status":"VERIFIED" if abs(difference)<=tolerance else "BLOCKED"}


def bank_preview(content:bytes,filename:str,organization_id:UUID,company_id:UUID,repository:AccountingWorkflowRepository,
                 tolerance:Decimal=Decimal("0.01"))->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="bap-bank-") as directory:
        path=Path(directory)/"statement.pdf";path.write_bytes(content);frame,account_text=LegacyBankStatementService().load(path)
    rows=[]
    for raw in frame.to_dict(orient="records"):
        row={key:("" if str(value)=="nan" else value) for key,value in raw.items()};description=str(row.get("Description") or "")
        transaction_type="Receipt" if _money(row.get("Deposit"))>0 else ("Payment" if _money(row.get("Withdrawal"))>0 else "")
        mappings=repository.mappings(organization_id,company_id,"bank","",transaction_type)
        matched=next((mapping for mapping in mappings if _match(description,mapping["pattern"],mapping["match_type"])),None)
        row["Type"]=transaction_type;row["Mapped Ledger"]=matched["ledger"] if matched else "Suspense";row["Matched By"]=matched["pattern"] if matched else "UNMATCHED_TO_SUSPENSE";row["Status"]="OK" if matched and transaction_type else "REVIEW"
        for key in ("Withdrawal","Deposit","Balance"):row[key]=str(_money(row.get(key)))
        rows.append(row)
    accounts=repository.bank_accounts(organization_id,company_id);selected=next((item for item in accounts if item["account_hint_token"] and str(item["account_hint_token"]) in account_text),accounts[0] if len(accounts)==1 else None)
    reconciliation=reconcile_bank_rows(rows,tolerance);mapping_ok=bool(rows and all(row["Status"]=="OK" for row in rows));account_ok=bool(selected)
    validation="VERIFIED" if reconciliation["status"]=="VERIFIED" and mapping_ok and account_ok else ("BLOCKED" if reconciliation["status"]=="BLOCKED" else "REVIEW")
    mapping_snapshot=hashlib.sha256(json.dumps([{key:row.get(key) for key in ("Description","Type","Mapped Ledger","Matched By")} for row in rows],sort_keys=True).encode()).hexdigest()
    return {"rows":rows,"reconciliation":reconciliation,"bank_account":{"id":selected["id"],"bank_ledger":selected["bank_ledger"],"account_hint":"••••"+str(selected["account_hint_token"])[-4:]} if selected else None,
        "validation_status":validation,"mapping_snapshot_sha256":mapping_snapshot,"export_allowed":validation=="VERIFIED"}


def bank_xml(preview:dict[str,Any])->bytes:
    if not preview["export_allowed"]:raise ValueError("bank XML is blocked until reconciliation, account, and mappings are verified")
    import pandas as pd
    settings={"bank_ledger":preview["bank_account"]["bank_ledger"],"unmatched_ledger":"Suspense",
        "voucher_number_prefix":"BANK-","create_missing_ledgers":False}
    return LegacyBankStatementService().build_xml(pd.DataFrame(preview["rows"]),settings).encode("utf-8")
