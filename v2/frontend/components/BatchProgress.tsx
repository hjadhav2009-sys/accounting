"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiContext, tenantHeaders } from "../lib/api";

type Batch = { status: string; total: number; processed: number; queued: number; running: number; verified: number; review: number; blocked: number; duplicate: number; failed: number; progress: string; accounting_summary?: Array<Record<string, string | number>> };

export function BatchProgress({ batchId, onComplete }: { batchId: string; onComplete: () => void }) {
  const context = apiContext(); const [batch, setBatch] = useState<Batch | null>(null);
  useEffect(() => {
    if (!context || !batchId) return;
    let active = true; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      const response = await fetch(`${context!.apiUrl}/api/v2/batches/${batchId}`, { headers: tenantHeaders(context!) });
      if (!response.ok || !active) return;
      const current: Batch = await response.json(); setBatch(current);
      if (["COMPLETED", "COMPLETED_WITH_ERRORS", "INTERRUPTED"].includes(current.status)) onComplete();
      else timer = setTimeout(() => void poll(), 1000);
    }
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [batchId, context, onComplete]);
  if (!batch) return <div className="batch-progress">Preparing durable batch…</div>;
  const outcomes = [["Verified", batch.verified, "VERIFIED"], ["Review", batch.review, "REVIEW"], ["Blocked", batch.blocked, "BLOCKED"], ["Duplicates", batch.duplicate, ""], ["Failed", batch.failed, "FAILED"]] as const;
  return <section className="batch-progress" aria-live="polite"><div className="batch-heading"><div><p className="eyebrow">Batch processing</p><h3>{batch.processed} / {batch.total} processed</h3></div><span>{batch.status}</span></div>
    <progress max={100} value={Number(batch.progress)}>{batch.progress}%</progress><div className="batch-counts">{outcomes.map(([label, value, status]) =>
      <Link key={label} href={status ? `/documents?status=${status}` : "/documents?duplicate_status=DUPLICATE"}><strong>{value}</strong><span>{label}</span></Link>)}
      <div><strong>{batch.running}</strong><span>Running</span></div><div><strong>{batch.queued}</strong><span>Queued</span></div></div>
    {!!batch.accounting_summary?.length && <div className="batch-summary"><strong>Compatible accounting groups</strong>{batch.accounting_summary.map((group, index) =>
      <p key={index}>{group.document_category} · {group.currency}: {group.document_count} documents · invoice total {group.invoice_total}</p>)}</div>}
  </section>;
}
