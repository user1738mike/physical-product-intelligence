import type { ReactNode } from "react";
import WorkspaceShell from "../../dashboard/shell";

export default async function OrganizationLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return (
    <WorkspaceShell key={organizationId} org={organizationId}>
      {children}
    </WorkspaceShell>
  );
}
