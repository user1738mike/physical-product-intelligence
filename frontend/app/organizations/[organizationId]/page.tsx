import { redirect } from "next/navigation";
import { organizationPath } from "../../../lib/workspace";

export default async function OrganizationPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  redirect(organizationPath(organizationId));
}
