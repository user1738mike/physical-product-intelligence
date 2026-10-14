import { ProductEditorPage } from "@/app/products/catalog";
export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const { organizationId } = await params;
  return <ProductEditorPage org={organizationId} />;
}
