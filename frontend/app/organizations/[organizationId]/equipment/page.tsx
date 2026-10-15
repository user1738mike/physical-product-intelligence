import { EquipmentList } from "@/app/compatibility/equipment";
export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return <EquipmentList org={organizationId} />;
}
