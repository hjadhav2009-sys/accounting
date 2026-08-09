import { AppShell } from "../../components/AppShell";
import { AiDashboard } from "../../components/AiDashboard";
import { PageHeader } from "../../components/PageHeader";

export default function AiPage(){return <AppShell active="AI Intelligence"><PageHeader title="Hybrid AI intelligence" description="Local-first proposals with privacy masking, free-quota enforcement, deterministic validation, and human approval."/><section className="status-banner"><div><span className="pulse"/><strong>Advisory only</strong></div><p>No general chatbot. No AI output can approve a template, post a voucher, or override accounting rules.</p></section><AiDashboard/></AppShell>}
