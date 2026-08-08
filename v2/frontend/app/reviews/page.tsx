import { AppShell } from "../../components/AppShell";
import { PageHeader } from "../../components/PageHeader";
import { ReviewWorkspace } from "../../components/ReviewWorkspace";

export default function ReviewsPage() {
  return <AppShell active="Review Queue"><PageHeader title="Review queue" description="Human decisions for unknown formats, OCR uncertainty, duplicate signals, and failed accounting checks." />
    <section className="panel"><ReviewWorkspace /></section></AppShell>;
}
