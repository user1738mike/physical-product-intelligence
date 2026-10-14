import { CatalogPage } from "@/app/products/catalog";
export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return <CatalogPage org={organizationId} />;
}
