"use client";

import { useEffect, useMemo, useState } from "react";
import { apiContext, tenantHeaders } from "../lib/api";

type Box = { x0: number; y0: number; x1: number; y1: number; page_width: number; page_height: number };
type Source = { page_number?: number; bounding_box?: Box };
type Field = { name: string; value: unknown; source?: Source; original_token?: string; confidence?: string; normalization?: string };
type Table = { table_index: number; bounding_box?: Box; rows?: Array<{ row_index: number; cells: Array<{ text: string }> }> };
type PageEvidence = { page_number: number; width: number; height: number; tables?: Table[] };
type Detail = { original_filename: string; status: string; document_type: string; supplier: string; invoice_number: string; page_count: number; quality_status: string; extraction_method: string; error_code: string | null };
type Extraction = { normalized_result?: { fields?: Field[]; pages?: PageEvidence[]; warnings?: string[] } };
type Validation = { status: string; calculations: Record<string, string>; issues: Array<{ code: string; severity: string; message: string }> };
type Selection = { label: string; page: number; box: Box; type: "FIELD" | "TABLE" | "VALIDATION_ERROR" | "OCR_REGION" };

function PageCanvas({ documentId, page, zoom, selection }: { documentId: string; page: number; zoom: number; selection: Selection | null }) {
  const context = apiContext();
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!context) return;
    let active = true; let objectUrl = "";
    fetch(`${context.apiUrl}/api/v2/documents/${documentId}/pages/${page}/image`, { headers: tenantHeaders(context) })
      .then((response) => { if (!response.ok) throw new Error("Page image unavailable"); return response.blob(); })
      .then((blob) => { objectUrl = URL.createObjectURL(blob); if (active) setUrl(objectUrl); })
      .catch(() => { if (active) setUrl(""); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [context, documentId, page]);
  const box = selection?.page === page ? selection.box : null;
  const overlay = box ? { left: `${box.x0 / box.page_width * 100}%`, top: `${box.y0 / box.page_height * 100}%`,
    width: `${(box.x1 - box.x0) / box.page_width * 100}%`, height: `${(box.y1 - box.y0) / box.page_height * 100}%` } : undefined;
  return <div className="page-pan"><div className="page-canvas" style={{ width: `${zoom}%` }}>
    {url ? <img src={url} alt={`Rendered PDF page ${page}`} /> : <div className="empty-table">Page preview unavailable.</div>}
    {overlay && <button className={`source-overlay overlay-${selection!.type.toLowerCase()}`} style={overlay} title={selection!.label}>{selection!.label}</button>}
  </div></div>;
}

export function DocumentDetail({ documentId }: { documentId: string }) {
  const context = apiContext();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [selection, setSelection] = useState<Selection | null>(null);
  useEffect(() => {
    if (!context) return;
    async function load() {
      try {
        const headers = tenantHeaders(context!);
        const [documentResponse, extractionResponse, validationResponse] = await Promise.all([
          fetch(`${context!.apiUrl}/api/v2/documents/${documentId}`, { headers }),
          fetch(`${context!.apiUrl}/api/v2/documents/${documentId}/extraction`, { headers }),
          fetch(`${context!.apiUrl}/api/v2/documents/${documentId}/validation`, { headers }),
        ]);
        if (!documentResponse.ok) throw new Error(`Document detail failed (${documentResponse.status})`);
        setDetail(await documentResponse.json());
        if (extractionResponse.ok) setExtraction(await extractionResponse.json());
        if (validationResponse.ok) setValidation(await validationResponse.json());
      } catch (reason) { setError(reason instanceof Error ? reason.message : "Document detail failed"); }
    }
    void load();
  }, [context, documentId]);
  const fields = extraction?.normalized_result?.fields || [];
  const tables = useMemo(() => (extraction?.normalized_result?.pages || []).flatMap((item) =>
    (item.tables || []).filter((table) => table.bounding_box).map((table) => ({ page: item.page_number, table }))), [extraction]);
  function selectSource(label: string, source: Source | undefined, type: Selection["type"] = "FIELD") {
    if (!source?.page_number || !source.bounding_box) { setSelection(null); return; }
    setPage(source.page_number); setSelection({ label, page: source.page_number, box: source.bounding_box, type });
  }
  if (!context) return <div className="config-state">Local tenant context is not configured.</div>;
  if (error) return <div className="config-state">{error}</div>;
  if (!detail) return <div className="config-state">Loading document evidence…</div>;
  return <>
    <section className="document-meta"><div><span className={`status status-${detail.status.toLowerCase()}`}>{detail.status}</span><h2>{detail.original_filename}</h2></div>
      <dl><div><dt>Classification</dt><dd>{detail.document_type || "Unclassified"}</dd></div><div><dt>Supplier</dt><dd>{detail.supplier || "—"}</dd></div>
        <div><dt>Invoice</dt><dd>{detail.invoice_number || "—"}</dd></div><div><dt>Extraction</dt><dd>{detail.extraction_method || "—"}</dd></div>
        <div><dt>Quality</dt><dd>{detail.quality_status || "—"}</dd></div><div><dt>Pages</dt><dd>{detail.page_count}</dd></div></dl></section>
    {detail.error_code === "FORMAT_UNKNOWN" && <section className="new-format-banner"><div><p className="eyebrow">New format detected</p><h2>Review-only format evidence</h2>
      <p>Native quality: {detail.quality_status || "unknown"} · OCR used: {detail.extraction_method === "LOCAL_OCR" ? "YES" : "NO"}. No approved format met deterministic routing rules.</p>
      <p>{extraction?.normalized_result?.warnings?.join(" · ") || "No similar approved candidate was selected."}</p></div><a className="primary primary-link" href={`/template-studio?documentId=${documentId}`}>Open Template Studio</a></section>}
    <section className="evidence-grid">
      <div className="pdf-stage"><div className="viewer-toolbar">
        <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}>Previous</button><span>Page {page} / {detail.page_count}</span>
        <button onClick={() => setPage(Math.min(detail.page_count, page + 1))} disabled={page === detail.page_count}>Next</button>
        <button onClick={() => setZoom(Math.max(50, zoom - 25))}>−</button><span>{zoom}%</span><button onClick={() => setZoom(Math.min(250, zoom + 25))}>+</button>
        <button onClick={() => setZoom(100)}>Fit width</button><button onClick={() => setZoom(70)}>Fit page</button></div>
        <PageCanvas documentId={documentId} page={page} zoom={zoom} selection={selection} />
      </div>
      <div className="evidence-panel"><p className="eyebrow">Source trace</p><h2>Detected fields</h2>
        {fields.map((field) => <button className="field-row" key={field.name} onClick={() => selectSource(field.name, field.source, field.name.startsWith("ocr_") ? "OCR_REGION" : "FIELD")}>
          <div><strong>{field.name}</strong><span>{String(field.value ?? "")}</span></div><small>{field.source?.bounding_box ? `Page ${field.source.page_number} · click to highlight` : "Source location unavailable"}</small>
          {field.original_token && <small>Raw: {field.original_token} · confidence {field.confidence || "—"}</small>}</button>)}
        {!fields.length && <p className="muted">No approved semantic fields were detected. Source location unavailable.</p>}
        {tables.length > 0 && <><p className="eyebrow validation-title">Tables</p>{tables.map(({ page: tablePage, table }) => <button className="field-row" key={`${tablePage}-${table.table_index}`}
          onClick={() => selectSource(`Table ${table.table_index + 1}`, { page_number: tablePage, bounding_box: table.bounding_box }, "TABLE")}>
          <strong>Table {table.table_index + 1}</strong><small>Page {tablePage} · {table.rows?.length || 0} rows · click to highlight</small></button>)}</>}
        <p className="eyebrow validation-title">Validation</p>
        {validation ? <><span className={`status status-${validation.status.toLowerCase()}`}>{validation.status}</span>
          {validation.issues.map((issue) => <div className="issue" key={`${issue.code}-${issue.message}`}><strong>{issue.code}</strong><p>{issue.message}</p></div>)}</>
          : <p className="muted">Validation has not produced a report for this document.</p>}
      </div>
    </section>
  </>;
}
