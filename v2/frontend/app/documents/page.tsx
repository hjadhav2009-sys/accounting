import { AppShell } from "../../components/AppShell";
import { DocumentWorkspace } from "../../components/DocumentWorkspace";
import { PageHeader } from "../../components/PageHeader";

export default function DocumentsPage() {
  return <AppShell active="Documents"><PageHeader title="Document library" description="Upload, classify, extract, validate, and trace V2 accounting PDFs without changing the authoritative SQLite application." />
    <section className="panel"><DocumentWorkspace /></section></AppShell>;
}
