import Link from "next/link";
import { AppShell } from "../components/AppShell";
import { PageHeader } from "../components/PageHeader";
import { StatCard } from "../components/StatCard";
import { ReportWorkspace } from "../components/ReportWorkspace";

export default function Home() {
  const legacyUrl = process.env.NEXT_PUBLIC_LEGACY_URL || "http://localhost:8501";
  return <AppShell active="Dashboard">
    <PageHeader title="Document intelligence" description="A deterministic local-first intake and review workspace. Production SQLite remains authoritative."
      actions={<a className="primary primary-link" href={legacyUrl}>Open legacy workspace</a>} />
    <section className="status-banner"><div><span className="pulse" /><strong>Phase 5 architecture</strong></div><p>Hybrid AI proposals are gated by privacy, quota, deterministic validation, and human approval. Runtime certification is partial.</p></section>
    <section className="stats"><StatCard icon="D" label="Documents" value="V2" detail="Tenant-scoped library" /><StatCard icon="E" label="Extraction" value="Local" detail="Native text, then local OCR" />
      <StatCard icon="V" label="Validation" value="Rules" detail="Decimal accounting checks" /><StatCard icon="R" label="Review" value="Human" detail="No silent guesses" /></section>
    <section className="lower-grid"><div className="panel"><p className="eyebrow">Start here</p><h2>Controlled document intake</h2><p className="muted">Upload one PDF or a batch. Every file is isolated, hashed, routed, and surfaced with evidence.</p><Link className="primary primary-link action-link" href="/documents">Open document library</Link></div>
      <div className="panel controls"><p className="eyebrow">Safety posture</p><h2>Authority boundaries</h2><dl><div><dt>Legacy SQLite</dt><dd>Authoritative</dd></div><div><dt>PostgreSQL</dt><dd>V2 metadata</dd></div><div><dt>PDF storage</dt><dd>Filesystem</dd></div><div><dt>AI</dt><dd>Advisory only</dd></div></dl><Link className="primary-link" href="/ai">Open AI status</Link></div></section>
    <section className="panel action-link"><p className="eyebrow">Live V2 status</p><h2>Tenant document outcomes</h2><ReportWorkspace /></section>
  </AppShell>;
}
