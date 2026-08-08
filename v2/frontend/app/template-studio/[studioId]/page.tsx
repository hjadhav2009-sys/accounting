import { TemplateStudio } from "../../../components/TemplateStudio";

export default async function TemplateStudioPage({ params }: { params: Promise<{ studioId: string }> }) {
  const { studioId } = await params;
  return <TemplateStudio versionId={studioId} />;
}
