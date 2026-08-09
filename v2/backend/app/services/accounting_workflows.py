from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal,ROUND_HALF_UP
from typing import Any
from uuid import UUID,uuid4
from xml.sax.saxutils import escape

from ..document_intelligence.validation import AccountingValidationEngine,BankBalanceValidator,InvoiceTotalValidator,RequiredFieldValidator
from ..domain.mapping import mapping_matches,normalize_platform,normalize_text


class MoneyParseError(ValueError):
    def __init__(self,field:str,raw:Any)->None:
        self.field,self.raw=field,raw
        super().__init__(f"{field} contains a malformed accounting amount")


def _money(value:Any,field:str="amount")->Decimal:
    if value is None or (isinstance(value,str) and not value.strip()):return Decimal("0.00")
    try:
        parsed=Decimal(str(value).replace(",","").strip())
        if not parsed.is_finite():raise ValueError("non-finite")
        return parsed.quantize(Decimal("0.01"),ROUND_HALF_UP)
    except Exception as exc:raise MoneyParseError(field,value) from exc


def _normalize_money_fields(row:dict[str,Any],fields:tuple[str,...])->list[dict[str,Any]]:
    errors=[]
    for key in fields:
        raw=row.get(key)
        try:row[key]=str(_money(raw,key))
        except MoneyParseError as exc:errors.append({"field":key,"raw_value":str(exc.raw),"code":"MALFORMED_MONEY"})
    return errors


def _match(text:str,pattern:str,match_type:str)->bool:
    return mapping_matches(text,pattern,match_type)


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
                    (mapping_id,organization_id,company_id,normalize_platform(tool),normalize_platform(platform),normalize_text(pattern),normalize_text(voucher_type),normalize_text(ledger),normalize_text(match_type).casefold()))
                mapping_id=cursor.fetchone()[0]
                cursor.execute("""INSERT INTO audit_logs(id,organization_id,company_id,actor_id,action,entity_type,
                    entity_id,new_reference,reason,source_context) VALUES(%s,%s,%s,%s,'MAPPING_CHANGED','ledger_mapping',
                    %s,%s,'authorized V2 mapping update',%s::jsonb)""",(uuid4(),organization_id,company_id,actor_id,
                    str(mapping_id),hashlib.sha256(ledger.strip().encode()).hexdigest(),json.dumps({"tool":tool,"platform":platform,"pattern":pattern,"match_type":match_type})))
            connection.commit();return mapping_id
        except Exception:connection.rollback();raise
        finally:connection.close()


def marketplace_preview(normalized:dict[str,Any],filename:str,organization_id:UUID,company_id:UUID,repository:AccountingWorkflowRepository)->dict[str,Any]:
    profile=repository.company_profile(organization_id,company_id)
    if not profile:raise ValueError("company is not available")
    source_rows=list(normalized.get("marketplace_rows") or normalized.get("items") or [])
    platform=str(normalized.get("platform") or "unknown");document_type=str(normalized.get("document_type") or "")
    invoice=str(normalized.get("invoice_number") or "");date=str(normalized.get("invoice_date") or "")
    native_rows=[]
    for item in source_rows:
        taxable=item.get("Taxable",item.get("taxable",""));cgst=item.get("CGST",item.get("cgst","0"))
        sgst=item.get("SGST",item.get("sgst","0"));igst=item.get("IGST",item.get("igst","0"))
        total=item.get("Total",item.get("total",""))
        native_rows.append({"Source PDF":filename,"Platform":item.get("Platform",item.get("platform",platform)),
            "PDF Doc Type":item.get("PDF Doc Type",item.get("document_type",document_type)),
            "Description":item.get("Description",item.get("description","")),"Invoice No":item.get("Invoice No",invoice),
            "Date":item.get("Date",date),"Taxable":taxable,"CGST":cgst,"SGST":sgst,"IGST":igst,"Total":total,
            "Import?":item.get("Import?",True),"Issue":item.get("Issue","")})
    rows=[];parse_errors=[]
    for index,raw in enumerate(native_rows):
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
        money_errors=_normalize_money_fields(row,("Taxable","CGST","SGST","IGST","Total"))
        for error in money_errors:error["row"]=index+1
        parse_errors.extend(money_errors)
        if money_errors:row["Status"]="BLOCKED";row["Issue"]="; ".join(filter(None,[row.get("Issue",""),"MALFORMED_MONEY"]))
        rows.append(row)
    mapping_snapshot=hashlib.sha256(json.dumps([{key:row.get(key) for key in ("Platform","PDF Doc Type","Description","Mapped Ledger","Matched By","Tally Voucher Type")} for row in rows],sort_keys=True).encode()).hexdigest()
    totals={key:(str(sum((_money(row.get(key),key) for row in rows),Decimal("0"))) if not any(error["field"]==key for error in parse_errors) else None) for key in ("Taxable","CGST","SGST","IGST","Total")}
    canonical={"invoice_total":totals["Total"],"taxable_total":totals["Taxable"],
        "tax_buckets":[{"tax_type":kind,"tax":row[kind],"taxable":row["Taxable"],"base_partition_id":f"row:{index}"}
            for index,row in enumerate(rows) for kind in ("CGST","SGST","IGST") if not parse_errors and _money(row[kind],kind)],
        "document_type":str(rows[0].get("PDF Doc Type") or "") if rows else ""}
    accounting=AccountingValidationEngine((RequiredFieldValidator(("invoice_total",)),InvoiceTotalValidator())).validate(canonical) if rows and not parse_errors else None
    classification_ok=all((str(row.get("PDF Doc Type")).casefold(),str(row.get("Tally Voucher Type")).casefold()) in
        {("tax invoice","purchase"),("credit note","debit note")} for row in rows)
    verified=bool(rows and not parse_errors and classification_ok and all(row["Status"]=="OK" for row in rows) and accounting and accounting.status=="VERIFIED")
    status="VERIFIED" if verified else ("BLOCKED" if parse_errors or (accounting and accounting.status=="BLOCKED") else "REVIEW")
    accounting_result=({"status":accounting.status,"findings":[{"validator":item.validator,"status":item.status,
        "message":item.message,"error_code":item.error_code.value if item.error_code else None} for item in accounting.findings],
        "calculations":accounting.calculations} if accounting else None)
    return {"rows":rows,"totals":totals,"validation_status":status,"parse_errors":parse_errors,
        "accounting_validation":accounting_result,"mapping_snapshot_sha256":mapping_snapshot,
        "export_allowed":verified,"profile":profile}


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
    credits=sum((_money(row.get("Deposit"),"Deposit") for row in rows),Decimal("0"));debits=sum((_money(row.get("Withdrawal"),"Withdrawal") for row in rows),Decimal("0"))
    first=rows[0];opening=_money(first.get("Balance"),"Balance")-_money(first.get("Deposit"),"Deposit")+_money(first.get("Withdrawal"),"Withdrawal")
    statement=_money(rows[-1].get("Balance"),"Balance");calculated=(opening+credits-debits).quantize(Decimal("0.01"));difference=(calculated-statement).quantize(Decimal("0.01"))
    transactions=[{"credit":row.get("Deposit"),"debit":row.get("Withdrawal"),"balance":row.get("Balance"),
                   "narration":row.get("Description")} for row in rows]
    report=AccountingValidationEngine((BankBalanceValidator(tolerance),)).validate({"opening_balance":opening,
        "closing_balance":statement,"bank_transactions":transactions})
    return {"opening":str(opening),"credits":str(credits),"debits":str(debits),"calculated_closing":str(calculated),
        "statement_closing":str(statement),"difference":str(difference),"status":report.status,
        "findings":[{"validator":item.validator,"status":item.status,"message":item.message} for item in report.findings]}


def bank_preview(normalized:dict[str,Any],filename:str,organization_id:UUID,company_id:UUID,repository:AccountingWorkflowRepository,
                 tolerance:Decimal=Decimal("0.01"))->dict[str,Any]:
    source_rows=list(normalized.get("bank_transactions") or normalized.get("transactions") or normalized.get("items") or [])
    account_text=json.dumps(normalized,default=str,ensure_ascii=False)
    rows=[];parse_errors=[]
    for index,item in enumerate(source_rows):
        raw={"Txn Date":item.get("Txn Date",item.get("date","")),
             "Description":item.get("Description",item.get("narration",item.get("description",""))),
             "Withdrawal":item.get("Withdrawal",item.get("debit","0")),
             "Deposit":item.get("Deposit",item.get("credit","0")),
             "Balance":item.get("Balance",item.get("balance",""))}
        row={key:("" if str(value)=="nan" else value) for key,value in raw.items()};description=str(row.get("Description") or "")
        money_errors=_normalize_money_fields(row,("Withdrawal","Deposit","Balance"))
        for error in money_errors:error["row"]=index+1
        parse_errors.extend(money_errors)
        transaction_type=""
        if not money_errors:transaction_type="Receipt" if _money(row.get("Deposit"),"Deposit")>0 else ("Payment" if _money(row.get("Withdrawal"),"Withdrawal")>0 else "")
        mappings=repository.mappings(organization_id,company_id,"bank","",transaction_type)
        matched=next((mapping for mapping in mappings if _match(description,mapping["pattern"],mapping["match_type"])),None)
        row["Type"]=transaction_type;row["Mapped Ledger"]=matched["ledger"] if matched else "Suspense";row["Matched By"]=matched["pattern"] if matched else "UNMATCHED_TO_SUSPENSE";row["Status"]="BLOCKED" if money_errors else ("OK" if matched and transaction_type else "REVIEW")
        rows.append(row)
    accounts=repository.bank_accounts(organization_id,company_id);selected=next((item for item in accounts if item["account_hint_token"] and str(item["account_hint_token"]) in account_text),accounts[0] if len(accounts)==1 else None)
    try:reconciliation=reconcile_bank_rows(rows,tolerance) if not parse_errors else {"status":"BLOCKED","findings":[]}
    except MoneyParseError:reconciliation={"status":"BLOCKED","findings":[]}
    mapping_ok=bool(rows and all(row["Status"]=="OK" for row in rows));account_ok=bool(selected)
    validation="VERIFIED" if reconciliation["status"]=="VERIFIED" and mapping_ok and account_ok else ("BLOCKED" if parse_errors or reconciliation["status"]=="BLOCKED" else "REVIEW")
    mapping_snapshot=hashlib.sha256(json.dumps([{key:row.get(key) for key in ("Description","Type","Mapped Ledger","Matched By")} for row in rows],sort_keys=True).encode()).hexdigest()
    return {"rows":rows,"reconciliation":reconciliation,"bank_account":{"id":selected["id"],"bank_ledger":selected["bank_ledger"],"account_hint":"••••"+str(selected["account_hint_token"])[-4:]} if selected else None,
        "validation_status":validation,"parse_errors":parse_errors,"mapping_snapshot_sha256":mapping_snapshot,"export_allowed":validation=="VERIFIED"}


def bank_xml(preview:dict[str,Any])->bytes:
    if not preview["export_allowed"]:raise ValueError("bank XML is blocked until reconciliation, account, and mappings are verified")
    bank=str(preview["bank_account"]["bank_ledger"]);messages=[]
    for index,row in enumerate(preview["rows"],1):
        credit=_money(row.get("Deposit"),"Deposit");debit=_money(row.get("Withdrawal"),"Withdrawal")
        voucher="Receipt" if credit>0 else "Payment";amount=credit if credit>0 else debit
        counter=str(row.get("Mapped Ledger") or "");date=escape(str(row.get("Txn Date") or ""))
        narration=escape(str(row.get("Description") or ""));bank_amount=amount if voucher=="Receipt" else -amount
        entries=_ledger_xml(bank,bank_amount)+_ledger_xml(counter,-bank_amount)
        messages.append(f'<TALLYMESSAGE xmlns:UDF="TallyUDF"><VOUCHER VCHTYPE="{voucher}" ACTION="Create"><DATE>{date}</DATE><VOUCHERTYPENAME>{voucher}</VOUCHERTYPENAME><VOUCHERNUMBER>BANK-{index:05d}</VOUCHERNUMBER><NARRATION>{narration}</NARRATION>{entries}</VOUCHER></TALLYMESSAGE>')
    return ("<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC>"
        "<REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC><REQUESTDATA>"+"".join(messages)+
        "</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>").encode("utf-8")
