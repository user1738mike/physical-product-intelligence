import { EquipmentDetail } from "@/app/compatibility/equipment";
export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string; equipmentId: string }>;
}) {
  const { organizationId, equipmentId } = await params;
  return <EquipmentDetail org={organizationId} id={equipmentId} />;
}
