import Link from "next/link";
import { CompanySwitcher } from "./CompanySwitcher";
import { FinancialYearSwitcher } from "./FinancialYearSwitcher";
import { ReviewBadge } from "./ReviewBadge";

const navigation = [
  ["Dashboard", "/"], ["Documents", "/documents"], ["Review Queue", "/reviews"],
  ["Templates", "/templates"], ["Reports", "/reports"], ["PDF to Excel", "#"], ["Invoice Converter", "#"],
  ["Marketplace XML", "#"], ["Bank Statement XML", "#"], ["Database / Masters", "#"],
  ["Users", "#"], ["Settings", "#"],
] as const;

export function AppShell({ active, children }: { active: string; children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span>BA</span><div><strong>Business Automation</strong><small>Document intelligence</small></div></div>
        <nav aria-label="Primary navigation">
          {navigation.map(([label, href], index) => (
            <Link href={href} className={active === label ? "active" : ""} key={label}
              aria-current={active === label ? "page" : undefined} prefetch={href !== "#"}>
              <span className="nav-mark" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>{label}
              {label === "Review Queue" && <ReviewBadge count={0} />}
            </Link>
          ))}
        </nav>
        <div className="legacy-note"><span className="pulse" />Legacy production remains authoritative</div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <CompanySwitcher /><FinancialYearSwitcher />
          <div className="global-search"><span className="muted">PostgreSQL V2 development workspace</span></div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
