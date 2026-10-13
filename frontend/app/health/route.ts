export const dynamic = "force-dynamic";

export function GET() {
  return Response.json(
    { status: "ok", service: "frontend" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
