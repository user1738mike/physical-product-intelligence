import OrganizationSettings from "../../settings";

export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return <OrganizationSettings org={organizationId} />;
}
