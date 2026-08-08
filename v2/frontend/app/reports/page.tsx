import { AppShell } from "../../components/AppShell";
import { PageHeader } from "../../components/PageHeader";
import { ReportWorkspace } from "../../components/ReportWorkspace";

export default function ReportsPage() {
  return <AppShell active="Reports"><PageHeader title="Document intelligence report" description="Tenant-scoped processing outcomes and runtime measurements from PostgreSQL V2 metadata." />
    <ReportWorkspace /></AppShell>;
}
