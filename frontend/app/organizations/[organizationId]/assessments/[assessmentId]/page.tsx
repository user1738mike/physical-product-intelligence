import { AssessmentDetail } from "@/app/compatibility/assessments";
export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string; assessmentId: string }>;
}) {
  const { organizationId, assessmentId } = await params;
  return <AssessmentDetail org={organizationId} id={assessmentId} />;
}
