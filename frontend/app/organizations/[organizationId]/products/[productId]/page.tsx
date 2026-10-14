import { ProductDetailPage } from "@/app/products/detail";
export default async function Page({
  params,
}: {
  params: Promise<{ organizationId: string; productId: string }>;
}) {
  const { organizationId, productId } = await params;
  return <ProductDetailPage org={organizationId} id={productId} />;
}
