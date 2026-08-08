import { AppShell } from "../../../components/AppShell";
import { DocumentDetail } from "../../../components/DocumentDetail";
import { PageHeader } from "../../../components/PageHeader";

export default async function DocumentPage({ params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = await params;
  return <AppShell active="Documents"><PageHeader title="Document evidence" description="PDF source, extracted fields, coordinate trace, and deterministic accounting checks." />
    <DocumentDetail documentId={documentId} /></AppShell>;
}
