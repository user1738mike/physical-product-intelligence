import { AssessmentWorkspace } from "@/app/compatibility/assessments";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ organizationId: string }>;
  searchParams: Promise<{ parent?: string }>;
}) {
  const { organizationId } = await params;
  const { parent } = await searchParams;
  return <AssessmentWorkspace org={organizationId} parent={parent} />;
}
