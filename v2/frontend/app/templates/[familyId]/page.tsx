import { AppShell } from "../../../components/AppShell";
import { TemplateFamilyDetail } from "../../../components/TemplateLibrary";

export default async function TemplateFamilyPage({ params }: { params: Promise<{ familyId: string }> }) {
  const { familyId } = await params;
  return <AppShell active="Templates"><TemplateFamilyDetail familyId={familyId} /></AppShell>;
}
