import { ImportList } from "@/app/imports/workspace";

export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return <ImportList org={organizationId} />;
}
