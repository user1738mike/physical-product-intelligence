import BillingPage from "@/app/billing/billing";

export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return <BillingPage org={organizationId} />;
}
