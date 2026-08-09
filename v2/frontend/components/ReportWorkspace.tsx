"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiContext, tenantHeaders } from "../lib/api";

type Report = {
  documents: { total: number; statuses: Record<string, number>; unknown_formats: number };
  invoices: Record<string, string | number>; marketplace: Record<string, string | number>;
  bank: Record<string, string | number>; processing: Record<string, string | number>;
  users:{activity:Array<{id:string;display_name:string;email:string;documents:number;reviews:number}>};
  ai:Record<string,string|number>;exports:{types:Record<string,{count:number;last_exported_at:string}>};
};
type FormatHealth = { family_id: string; family: string; documents_seen: number; approved_versions: number; latest_version: number | null; success_rate: string; review_rate: string; ocr_rate: string; unknown_variations: number; last_seen: string };

function Metric({ label, value, href }: { label: string; value: string | number; href?: string }) {
  const body = <><small>{label}</small><p className="stat-value">{value}</p></>;
  return href ? <Link className="stat-card metric-link" href={href}>{body}</Link> : <div className="stat-card">{body}</div>;
}

export function ReportWorkspace() {
  const context = apiContext(); const [report, setReport] = useState<Report | null>(null);
  const [formats, setFormats] = useState<FormatHealth[]>([]); const [error, setError] = useState("");
  const [dates, setDates] = useState({ date_from: "", date_to: "" });
  const [financialYearId,setFinancialYearId]=useState("");
  useEffect(()=>{setFinancialYearId(window.sessionStorage.getItem("ba_financial_year")||"")},[]);
  const query = useMemo(() => { const value = new URLSearchParams(); if(financialYearId)value.set("financial_year_id",financialYearId);else{if(dates.date_from)value.set("date_from",dates.date_from);if(dates.date_to)value.set("date_to",dates.date_to)} return value.toString(); }, [dates,financialYearId]);
  useEffect(() => { if (!context) return; Promise.all([
    fetch(`${context.apiUrl}/api/v2/reports/unified${query ? `?${query}` : ""}`, { headers: tenantHeaders(context) }),
    fetch(`${context.apiUrl}/api/v2/reports/format-health`, { headers: tenantHeaders(context) }),
  ]).then(async ([reportResponse, formatResponse]) => {
    if (!reportResponse.ok || !formatResponse.ok) throw new Error("Unified report failed");
    setReport(await reportResponse.json()); setFormats((await formatResponse.json()).items);
  }).catch((reason) => setError(String(reason))); }, [context, query]);
  if (!context) return <div className="config-state">Local tenant context is not configured.</div>;
  if (error) return <div className="config-state">{error}</div>;
  if (!report) return <div className="config-state">Loading report…</div>;
  return <div className="report-sections">
    <div className="document-filters"><label><span>Report from</span><input type="date" value={dates.date_from} onChange={(event)=>setDates({...dates,date_from:event.target.value})}/></label>
      <label><span>Report to</span><input type="date" value={dates.date_to} onChange={(event)=>setDates({...dates,date_to:event.target.value})}/></label>
      <button className="filter-button" onClick={()=>setDates({date_from:"",date_to:""})}>Clear dates</button></div>
    <section><p className="eyebrow">Documents</p><div className="stats report-stats"><Metric label="Total" value={report.documents.total} href="/documents" />
      <Metric label="Verified" value={report.documents.statuses.VERIFIED || 0} href="/documents?status=VERIFIED"/><Metric label="Review" value={report.documents.statuses.REVIEW || 0} href="/reviews?status=OPEN"/>
      <Metric label="Blocked" value={report.documents.statuses.BLOCKED || 0} href="/documents?status=BLOCKED"/><Metric label="Duplicates" value={report.documents.statuses.DUPLICATE || 0} href="/documents?duplicate_status=DUPLICATE"/>
      <Metric label="Unknown formats" value={report.documents.unknown_formats} href="/reports#format-health"/></div></section>
    <section><p className="eyebrow">Invoices and GST</p><div className="stats report-stats"><Metric label="Invoices" value={report.invoices.count}/><Metric label="Taxable" value={report.invoices.taxable}/>
      <Metric label="CGST" value={report.invoices.CGST}/><Metric label="SGST" value={report.invoices.SGST}/><Metric label="IGST" value={report.invoices.IGST}/><Metric label="Invoice total" value={report.invoices.invoice_total}/></div></section>
    <section><p className="eyebrow">Marketplace and bank</p><div className="stats report-stats"><Metric label="Marketplace docs" value={report.marketplace.document_count}/><Metric label="Marketplace GST" value={report.marketplace.GST}/><Metric label="Unmapped market" value={report.marketplace.unmapped} href="/reviews?reason=UNKNOWN_LEDGER"/>
      <Metric label="Bank transactions" value={report.bank.transactions}/><Metric label="Credits" value={report.bank.credits}/><Metric label="Debits" value={report.bank.debits}/><Metric label="Bank failures" value={report.bank.reconciliation_failures} href="/reviews?reason=BANK_RECONCILIATION_FAILED"/></div></section>
    <section><p className="eyebrow">Processing</p><div className="stats report-stats"><Metric label="Success rate %" value={report.processing.success_rate}/><Metric label="Review rate %" value={report.processing.review_rate}/><Metric label="OCR stages" value={report.processing.OCR_usage}/><Metric label="Average ms" value={report.processing.average_duration_ms}/></div></section>
    <section><p className="eyebrow">AI and exports</p><div className="stats report-stats"><Metric label="Local AI events" value={report.ai.local_jobs}/><Metric label="Cloud AI events" value={report.ai.cloud_jobs}/><Metric label="Cloud avoided" value={report.ai.cloud_avoided}/><Metric label="Quota used" value={report.ai.used_units}/><Metric label="Excel exports" value={report.exports.types.EXCEL?.count||0}/><Metric label="Marketplace XML" value={report.exports.types.MARKETPLACE_XML?.count||0}/><Metric label="Bank XML" value={report.exports.types.BANK_XML?.count||0}/></div></section>
    <section className="panel"><p className="eyebrow">User activity</p><h2>Documents and reviews</h2><div className="table-wrap"><table><thead><tr><th>User</th><th>Documents processed</th><th>Reviews resolved</th></tr></thead><tbody>{report.users.activity.map(user=><tr key={user.id}><td><strong>{user.display_name}</strong><small>{user.email}</small></td><td>{user.documents}</td><td>{user.reviews}</td></tr>)}</tbody></table></div></section>
    <section id="format-health" className="panel"><p className="eyebrow">Format health</p><h2>Read-only format intelligence</h2>
      <div className="table-wrap"><table><thead><tr><th>Family</th><th>Seen</th><th>Approved</th><th>Success</th><th>Review</th><th>OCR</th><th>Unknown</th><th>Last seen</th></tr></thead><tbody>
        {formats.map((format) => <tr key={format.family_id}><td><strong>{format.family}</strong></td><td>{format.documents_seen}</td><td>{format.approved_versions} / v{format.latest_version || "—"}</td><td>{format.success_rate}%</td><td>{format.review_rate}%</td><td>{format.ocr_rate}%</td><td>{format.unknown_variations}</td><td>{format.last_seen ? new Date(format.last_seen).toLocaleDateString() : "—"}</td></tr>)}</tbody></table>
        {!formats.length && <div className="empty-table">No format observations for this company.</div>}</div></section>
  </div>;
}
