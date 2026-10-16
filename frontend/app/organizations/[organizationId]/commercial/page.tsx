import PlanUsage from "@/app/commercial/usage";

export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return <PlanUsage org={organizationId} />;
}
