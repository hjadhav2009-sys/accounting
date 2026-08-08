import { CompanySwitcher } from "../components/CompanySwitcher";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { FilterBar } from "../components/FilterBar";
import { FinancialYearSwitcher } from "../components/FinancialYearSwitcher";
import { PageHeader } from "../components/PageHeader";
import { ReviewBadge } from "../components/ReviewBadge";
import { StatCard } from "../components/StatCard";

const navigation = [
  "Dashboard", "Documents", "PDF to Excel", "Invoice Converter", "Marketplace XML",
  "Bank Statement XML", "Template Studio", "Review Queue", "Reports",
  "Database / Masters", "Users", "Settings",
];

export default function Home() {
  const legacyUrl = process.env.NEXT_PUBLIC_LEGACY_URL || "http://localhost:8501";
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span>BA</span><div><strong>Business Automation</strong><small>Platform foundation</small></div></div>
        <nav aria-label="Primary navigation">
          {navigation.map((item, index) => (
            <a href="#" className={index === 0 ? "active" : ""} key={item} aria-current={index === 0 ? "page" : undefined}>
              <span className="nav-mark" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>{item}
              {item === "Review Queue" && <ReviewBadge count={0} />}
            </a>
          ))}
        </nav>
        <div className="legacy-note"><span className="pulse" />Legacy production remains active</div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <CompanySwitcher />
          <FinancialYearSwitcher />
          <label className="global-search"><span className="sr-only">Global search</span><input type="search" placeholder="Global search" /></label>
          <button className="notification" type="button" aria-label="Review notifications">Review <ReviewBadge count={0} /></button>
        </header>

        <main>
          <PageHeader
            title="Operations dashboard"
            description="A controlled view of document and accounting workflows. V2 is isolated while the certified legacy system remains authoritative."
            actions={<a className="primary primary-link" href={legacyUrl}>Open legacy workspace</a>}
          />

          <section className="status-banner" aria-label="Platform status">
            <div><span className="pulse" /><strong>Foundation mode</strong></div>
            <p>PostgreSQL cutover and AI processing are disabled. No production data is exposed here.</p>
          </section>

          <section className="stats" aria-label="Operational summary">
            <StatCard icon="D" label="Documents" value="—" detail="Awaiting V2 connection" />
            <StatCard icon="V" label="Verified" value="—" detail="Deterministic validation" />
            <StatCard icon="R" label="Review queue" value="0" detail="No V2 review tasks" />
            <StatCard icon="B" label="Blocked" value="0" detail="No active V2 jobs" />
          </section>

          <section className="panel">
            <div className="panel-heading"><div><p className="eyebrow">Document operations</p><h2>Workflow readiness</h2></div><span className="muted">Foundation data only</span></div>
            <FilterBar />
            <DataTable />
          </section>

          <section className="lower-grid">
            <div className="panel"><p className="eyebrow">Activity</p><h2>Processing jobs</h2><EmptyState /></div>
            <div className="panel controls"><p className="eyebrow">Control plane</p><h2>Safety posture</h2>
              <dl><div><dt>Legacy authority</dt><dd>Enabled</dd></div><div><dt>PostgreSQL cutover</dt><dd>Disabled</dd></div><div><dt>Cloud AI</dt><dd>Disabled</dd></div><div><dt>Template Studio</dt><dd>Placeholder</dd></div></dl>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
