export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Context = { params: Promise<{ path: string[] }> };
const MAX_BODY_BYTES = 64 * 1024;
const REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "x-csrftoken",
  "origin",
  "referer",
  "x-request-id",
];
const RESPONSE_HEADERS = [
  "content-type",
  "vary",
  "allow",
  "retry-after",
  "www-authenticate",
  "x-request-id",
  "location",
];

function problem(status: number, detail: string) {
  return Response.json(
    { detail },
    { status, headers: { "Cache-Control": "private, no-store" } },
  );
}

class BodyTooLarge extends Error {}

async function readBody(request: Request) {
  if (Number(request.headers.get("content-length")) > MAX_BODY_BYTES)
    throw new BodyTooLarge();
  if (!request.body) return undefined;
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) {
        await reader.cancel();
        throw new BodyTooLarge();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body.buffer;
}

async function forward(request: Request, context: Context) {
  const { path } = await context.params;
  if (
    path.some(
      (segment) => segment === "." || segment === ".." || segment.includes("/"),
    )
  ) {
    return problem(400, "Invalid API path.");
  }
  try {
    const target = new URL(
      process.env.API_BACKEND_ORIGIN ?? "http://127.0.0.1:8000",
    );
    if (
      !["http:", "https:"].includes(target.protocol) ||
      target.username ||
      target.password
    ) {
      return problem(502, "Backend unavailable.");
    }
    target.pathname = `/api/v1/${path.map(encodeURIComponent).join("/")}/`;
    target.search = new URL(request.url).search;
    target.hash = "";
    const headers = new Headers();
    for (const name of REQUEST_HEADERS) {
      const value = request.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    const method = request.method.toUpperCase();
    const body = ["GET", "HEAD"].includes(method)
      ? undefined
      : await readBody(request);
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(30_000),
    });
    const responseHeaders = new Headers({
      "Cache-Control": "private, no-store",
    });
    for (const name of RESPONSE_HEADERS) {
      const value = upstream.headers.get(name);
      if (value !== null) responseHeaders.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      responseHeaders.append("set-cookie", cookie);
    const empty =
      method === "HEAD" || [204, 205, 304].includes(upstream.status);
    return new Response(empty ? null : upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    if (error instanceof BodyTooLarge)
      return problem(413, "Request body too large.");
    // Do not log headers, bodies, cookies, credentials or backend error details.
    console.error("backend_proxy_unavailable");
    return problem(502, "Backend unavailable.");
  }
}

export {
  forward as GET,
  forward as HEAD,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
  forward as OPTIONS,
};
