"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiContext, tenantHeaders } from "../lib/api";
import { BatchProgress } from "./BatchProgress";

type DocumentRow = {
  document_id: string; original_filename: string; status: string; supplier: string;
  invoice_number: string; document_type: string; page_count: number; created_at: string;
};

export function DocumentWorkspace() {
  const context = apiContext();
  const [items, setItems] = useState<DocumentRow[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [batchId, setBatchId] = useState("");
  const [filters, setFilters] = useState({ search: "", status: "", document_type: "", supplier: "", date_from: "", date_to: "", validation_status: "", review_status: "", duplicate_status: "", format_family_id: "", uploaded_by: "" });
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setFilters((current) => Object.fromEntries(Object.keys(current).map((key) => [key, query.get(key) || ""])) as typeof current);
  }, []);
  const queryString = useMemo(() => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value && (!key.endsWith("_id") || /^[0-9a-f-]{36}$/i.test(value))) query.set(key, value); });
    return query.toString();
  }, [filters]);
  const load = useCallback(async () => {
    if (!context) return;
    setLoading(true);
    try {
      const response = await fetch(`${context.apiUrl}/api/v2/documents${queryString ? `?${queryString}` : ""}`, { headers: tenantHeaders(context) });
      if (!response.ok) throw new Error(`Document list failed (${response.status})`);
      setItems((await response.json()).items);
      setMessage("");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Document list failed"); }
    finally { setLoading(false); }
  }, [context, queryString]);

  useEffect(() => { window.history.replaceState(null, "", `${window.location.pathname}${queryString ? `?${queryString}` : ""}`); void load(); }, [load, queryString]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!context) return;
    const input = event.currentTarget.elements.namedItem("documents") as HTMLInputElement;
    const files = Array.from(input.files || []);
    if (!files.length) return;
    setLoading(true);
    const form = new FormData();
    const endpoint = files.length === 1 ? "/api/v2/documents/upload" : "/api/v2/documents/batch";
    files.forEach((file) => form.append(files.length === 1 ? "file" : "files", file));
    try {
      const response = await fetch(`${context.apiUrl}${endpoint}`, { method: "POST", headers: tenantHeaders(context), body: form });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.detail || `Upload failed (${response.status})`);
      setMessage(files.length === 1 ? `Document routed to ${payload.status}.` : `Batch ${payload.batch_id} queued with ${payload.total} documents.`);
      if (payload.batch_id) setBatchId(payload.batch_id);
      input.value = "";
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Upload failed"); }
    finally { setLoading(false); }
  }

  if (!context) return <div className="config-state"><strong>Local API context is not configured.</strong><p>Set NEXT_PUBLIC_ORGANIZATION_ID, NEXT_PUBLIC_COMPANY_ID, and NEXT_PUBLIC_USER_ID in the ignored frontend environment file.</p></div>;
  return <>
    <form className="upload-panel" onSubmit={upload}>
      <label><strong>Upload accounting PDFs</strong><span>Native text extraction runs first. Scans use local OCR only when installed.</span>
        <input name="documents" type="file" accept="application/pdf,.pdf" multiple required /></label>
      <button className="primary" disabled={loading}>{loading ? "Working…" : "Upload and process"}</button>
    </form>
    {message && <p className="inline-message" role="status">{message}</p>}
    {batchId && <BatchProgress batchId={batchId} onComplete={load} />}
    <div className="document-filters" aria-label="Document filters">
      <label><span>Search</span><input value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} placeholder="Filename, invoice, supplier" /></label>
      <label><span>Status</span><select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">All</option>{["VERIFIED","REVIEW","BLOCKED","FAILED","OCR_REQUIRED"].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label><span>Document type</span><input value={filters.document_type} onChange={(event) => setFilters({ ...filters, document_type: event.target.value })} /></label>
      <label><span>Supplier</span><input value={filters.supplier} onChange={(event) => setFilters({ ...filters, supplier: event.target.value })} /></label>
      <label><span>From</span><input type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} /></label>
      <label><span>To</span><input type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} /></label>
      <label><span>Validation</span><select value={filters.validation_status} onChange={(event) => setFilters({ ...filters, validation_status: event.target.value })}><option value="">All</option>{["VERIFIED","REVIEW","BLOCKED"].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label><span>Review</span><select value={filters.review_status} onChange={(event) => setFilters({ ...filters, review_status: event.target.value })}><option value="">All</option>{["OPEN","IN_PROGRESS","RESOLVED","REJECTED"].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label><span>Duplicate</span><select value={filters.duplicate_status} onChange={(event) => setFilters({ ...filters, duplicate_status: event.target.value })}><option value="">All</option><option>DUPLICATE</option><option>UNIQUE</option></select></label>
      <label><span>Format family ID</span><input value={filters.format_family_id} onChange={(event) => setFilters({ ...filters, format_family_id: event.target.value })} placeholder="Optional UUID" /></label>
      <label><span>Uploaded by</span><input value={filters.uploaded_by} onChange={(event) => setFilters({ ...filters, uploaded_by: event.target.value })} placeholder="Optional user UUID" /></label>
      <button className="filter-button" onClick={() => setFilters({ search: "", status: "", document_type: "", supplier: "", date_from: "", date_to: "", validation_status: "", review_status: "", duplicate_status: "", format_family_id: "", uploaded_by: "" })}>Clear all</button>
    </div>
    <div className="table-wrap"><table><thead><tr><th>Document</th><th>Type / supplier</th><th>Invoice</th><th>Pages</th><th>Status</th></tr></thead>
      <tbody>{items.map((item) => <tr key={item.document_id}><td><Link href={`/documents/${item.document_id}`}><strong>{item.original_filename}</strong></Link></td>
        <td>{item.document_type || "Unclassified"}<small>{item.supplier || "—"}</small></td><td>{item.invoice_number || "—"}</td><td>{item.page_count}</td>
        <td><span className={`status status-${item.status.toLowerCase()}`}>{item.status}</span></td></tr>)}</tbody></table>
      {!items.length && !loading && <div className="empty-table">No V2 documents have been registered for this company.</div>}</div>
  </>;
}
