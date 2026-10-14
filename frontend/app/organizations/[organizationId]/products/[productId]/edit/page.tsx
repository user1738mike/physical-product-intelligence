import { ProductEditorPage } from "@/app/products/catalog";
export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string; productId: string }>;
}) {
  const { organizationId, productId } = await params;
  return <ProductEditorPage org={organizationId} id={productId} />;
}
