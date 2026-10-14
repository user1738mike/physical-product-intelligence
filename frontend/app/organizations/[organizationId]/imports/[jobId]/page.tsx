import { ImportDetail } from "@/app/imports/workspace";

export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string; jobId: string }>;
}) {
  const { organizationId, jobId } = await params;
  return <ImportDetail org={organizationId} id={jobId} />;
}
