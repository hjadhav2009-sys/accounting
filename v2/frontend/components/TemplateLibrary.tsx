"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiContext, tenantHeaders } from "../lib/api";

type Family = { id: string; name: string; document_type: string; supplier?: string; latest_version?: number; latest_version_id?: string; latest_status?: string; documents_processed: number; verified: number; review: number; blocked: number; last_seen?: string };
type Version = { id: string; version: number; status: string; engine: string; updated_at: string; approval_evidence?: Record<string, unknown> };
type Detail = Family & { description: string; versions: Version[]; activity: Array<{ id: string; event_type: string; created_at: string }> };

export function TemplateLibrary() {
  const context = apiContext(); const [items, setItems] = useState<Family[]>([]); const [error, setError] = useState("");
  const [filters, setFilters] = useState({ search: "", document_type: "", status: "", supplier: "" });
  useEffect(() => { if (!context) return; const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
    fetch(`${context.apiUrl}/api/v2/templates?${query}`, { headers: tenantHeaders(context) }).then(async response => {
      if (!response.ok) throw new Error(`Templates failed (${response.status})`); setItems((await response.json()).items);
    }).catch(reason => setError(reason.message)); }, [context, filters]);
  if (!context) return <div className="config-state">Local tenant context is not configured.</div>;
  return <><div className="page-header"><div><p className="breadcrumb">Document intelligence / Templates</p><h1>Template Library</h1>
    <p>Measured format health, immutable version history, protected samples and deterministic extraction rules.</p></div>
    <div className="header-actions"><Link className="filter-button" href="/templates/routing">Routing diagnostic</Link> <Link className="primary primary-link" href="/template-studio">New template</Link></div></div>
    <section className="panel"><div className="document-filters">
      <label><span>Search</span><input value={filters.search} onChange={event => setFilters({...filters, search: event.target.value})} placeholder="Family or supplier" /></label>
      <label><span>Document type</span><select value={filters.document_type} onChange={event => setFilters({...filters, document_type: event.target.value})}><option value="">All</option><option>Tax Invoice</option><option>Marketplace</option><option>Bank Statement</option><option>Stock Transfer</option></select></label>
      <label><span>Status</span><select value={filters.status} onChange={event => setFilters({...filters, status: event.target.value})}><option value="">All</option>{["DRAFT","TESTING","APPROVED","DEPRECATED","REJECTED"].map(value => <option key={value}>{value}</option>)}</select></label>
      <label><span>Supplier / platform</span><input value={filters.supplier} onChange={event => setFilters({...filters, supplier: event.target.value})} /></label>
    </div>{error && <p className="inline-message">{error}</p>}
    <div className="table-wrap"><table><thead><tr><th>Format Family</th><th>Document Type</th><th>Latest</th><th>Status</th><th>Processed</th><th>Success</th><th>Review</th><th>Last Seen</th><th /></tr></thead><tbody>
      {items.map(item => { const measured = item.verified + item.review + item.blocked; const success = measured ? `${Math.round(item.verified / measured * 100)}%` : "No data";
        return <tr key={item.id}><td><strong>{item.name}</strong><small>{item.supplier || "No supplier constraint"}</small></td><td>{item.document_type}</td><td>{item.latest_version ? `v${item.latest_version}` : "—"}</td><td><span className={`status status-${(item.latest_status || "draft").toLowerCase()}`}>{item.latest_status || "DRAFT"}</span></td><td>{item.documents_processed}</td><td>{success}</td><td>{measured ? `${Math.round(item.review / measured * 100)}%` : "No data"}</td><td>{item.last_seen ? new Date(item.last_seen).toLocaleDateString() : "Never"}</td><td><Link href={`/templates/${item.id}`}>Open</Link></td></tr>; })}
    </tbody></table>{!items.length && <div className="empty-table">No template families match the current filters.</div>}</div></section></>;
}

export function TemplateFamilyDetail({ familyId }: { familyId: string }) {
  const context = apiContext(); const [detail, setDetail] = useState<Detail | null>(null); const [error, setError] = useState("");
  useEffect(() => { if (!context) return; fetch(`${context.apiUrl}/api/v2/templates/families/${familyId}`, { headers: tenantHeaders(context) })
    .then(async response => { if (!response.ok) throw new Error(`Family failed (${response.status})`); setDetail(await response.json()); }).catch(reason => setError(reason.message)); }, [context, familyId]);
  if (error) return <div className="config-state">{error}</div>; if (!detail) return <div className="config-state">Loading format family…</div>;
  return <><div className="page-header"><div><p className="breadcrumb">Templates / {detail.document_type}</p><h1>{detail.name}</h1><p>{detail.description || "No description supplied."}</p></div></div>
    <section className="lower-grid"><div className="panel"><p className="eyebrow">Version history</p><div className="version-list">{detail.versions.map(version => <div className="version-card" key={version.id}>
      <div><strong>v{version.version}</strong><span className={`status status-${version.status.toLowerCase()}`}>{version.status}</span><small>{version.engine.replaceAll("_", " ")}</small></div>
      <Link className="primary primary-link" href={`/template-studio/${version.id}`}>{version.status === "APPROVED" ? "Inspect" : "Open Studio"}</Link></div>)}</div></div>
      <div className="panel"><p className="eyebrow">Activity</p>{detail.activity?.map(item => <div className="activity-line" key={item.id}><strong>{item.event_type.replaceAll("_", " ")}</strong><small>{new Date(item.created_at).toLocaleString()}</small></div>)}</div></section></>;
}
