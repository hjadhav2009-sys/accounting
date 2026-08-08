"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiContext, tenantHeaders } from "../lib/api";

type Review = { review_id: string; document_id: string; original_filename: string; reason_code: string; severity: string; created_at: string };

export function ReviewWorkspace() {
  const context = apiContext();
  const [items, setItems] = useState<Review[]>([]);
  const [message, setMessage] = useState("");
  const [filters, setFilters] = useState({ status: "OPEN", reason: "", severity: "", assigned_to: "", date_from: "", date_to: "" });
  const query = useMemo(() => { const value = new URLSearchParams(); Object.entries(filters).forEach(([key, item]) => { if (item && (key !== "assigned_to" || /^[0-9a-f-]{36}$/i.test(item))) value.set(key, item); }); return value.toString(); }, [filters]);
  const load = useCallback(async () => {
    if (!context) return;
    try {
      const response = await fetch(`${context.apiUrl}/api/v2/reviews?${query}`, { headers: tenantHeaders(context) });
      if (!response.ok) throw new Error(`Review queue failed (${response.status})`);
      setItems((await response.json()).items);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Review queue failed"); }
  }, [context, query]);
  useEffect(() => { window.history.replaceState(null, "", `${window.location.pathname}?${query}`); void load(); }, [load, query]);

  async function resolve(reviewId: string) {
    if (!context) return;
    const note = window.prompt("Resolution note (required)");
    if (!note) return;
    const response = await fetch(`${context.apiUrl}/api/v2/reviews/${reviewId}/resolve`, {
      method: "POST", headers: { ...tenantHeaders(context), "Content-Type": "application/json" },
      body: JSON.stringify({ resolution_note: note, status: "RESOLVED" }),
    });
    if (!response.ok) { setMessage(`Resolution failed (${response.status})`); return; }
    await load();
  }

  if (!context) return <div className="config-state">Local tenant context is not configured.</div>;
  return <div className="review-list"><div className="document-filters">
    <label><span>Status</span><select value={filters.status} onChange={(event) => setFilters({...filters,status:event.target.value})}><option value="">All</option>{["OPEN","IN_PROGRESS","RESOLVED","REJECTED"].map((item)=><option key={item}>{item}</option>)}</select></label>
    <label><span>Reason</span><select value={filters.reason} onChange={(event) => setFilters({...filters,reason:event.target.value})}><option value="">All</option>{["UNKNOWN_FORMAT","OCR_LOW_CONFIDENCE","OCR_FAILED","QUANTITY_MISMATCH","GST_MISMATCH","TOTAL_MISMATCH","BANK_RECONCILIATION_FAILED","UNKNOWN_LEDGER","POSSIBLE_DUPLICATE","REQUIRED_FIELD_MISSING"].map((item)=><option key={item}>{item}</option>)}</select></label>
    <label><span>Severity</span><select value={filters.severity} onChange={(event) => setFilters({...filters,severity:event.target.value})}><option value="">All</option>{["INFO","REVIEW","BLOCKING"].map((item)=><option key={item}>{item}</option>)}</select></label>
    <label><span>Assignee ID</span><input value={filters.assigned_to} onChange={(event) => setFilters({...filters,assigned_to:event.target.value})} placeholder="Optional UUID"/></label>
    <label><span>From</span><input type="date" value={filters.date_from} onChange={(event) => setFilters({...filters,date_from:event.target.value})}/></label>
    <label><span>To</span><input type="date" value={filters.date_to} onChange={(event) => setFilters({...filters,date_to:event.target.value})}/></label>
    <button className="filter-button" onClick={()=>setFilters({status:"OPEN",reason:"",severity:"",assigned_to:"",date_from:"",date_to:""})}>Clear</button></div>
    {message && <p className="inline-message">{message}</p>}
    {items.map((item) => <article className="review-card" key={item.review_id}>
      <div><span className={`status status-${item.severity.toLowerCase()}`}>{item.severity}</span><h3>{item.reason_code.replaceAll("_", " ")}</h3>
        <p><Link href={`/documents/${item.document_id}`}>{item.original_filename}</Link></p></div>
      <button className="filter-button" onClick={() => void resolve(item.review_id)}>Resolve with note</button>
    </article>)}
    {!items.length && !message && <div className="empty-table">No open review tasks for this company.</div>}
  </div>;
}
