import IntegrationsPage from "@/app/integrations/integrations";

export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return <IntegrationsPage org={organizationId} />;
}
