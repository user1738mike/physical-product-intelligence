import DashboardOverview from "../../../dashboard/overview";
import { TenantFrame } from "../../../products/ui";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return (
    <TenantFrame org={organizationId}>
      <DashboardOverview org={organizationId} />
    </TenantFrame>
  );
}
