import { afterEach, expect, it, vi } from "vitest";
import { ingestion } from "../lib/ingestion";
import { GET, POST } from "../app/api/v1/[...path]/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it("uploads native multipart bytes with fresh CSRF without assigning a JSON content type", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ csrfToken: "masked-fixture" }))
    .mockResolvedValueOnce(Response.json({ id: "job" }));
  vi.stubGlobal("fetch", fetch);
  const source = new File(["sku,name\nA,Box\n"], "source.csv", {
    type: "text/csv",
  });
  await ingestion.upload("org", source);
  const options = fetch.mock.calls[1][1];
  expect(options.headers["X-CSRFToken"]).toBe("masked-fixture");
  expect(options.headers).not.toHaveProperty("Content-Type");
  expect(options.body).toBeInstanceOf(FormData);
  expect(options.body.get("file").name).toBe("source.csv");
  expect(options.credentials).toBe("same-origin");
});

it("allows bounded upload bodies only on the organization import collection", async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({ id: "job" }));
  vi.stubGlobal("fetch", fetch);
  vi.stubEnv("API_BACKEND_ORIGIN", "http://backend:8000");
  const body = "x".repeat(70 * 1024);
  const accepted = await POST(
    new Request("http://localhost/api/v1/organizations/org/imports/", {
      method: "POST",
      body,
    }),
    { params: Promise.resolve({ path: ["organizations", "org", "imports"] }) },
  );
  expect(accepted.status).toBe(200);
  const rejected = await POST(
    new Request("http://localhost/api/v1/organizations/org/products/", {
      method: "POST",
      body,
    }),
    { params: Promise.resolve({ path: ["organizations", "org", "products"] }) },
  );
  expect(rejected.status).toBe(413);
  const huge = await POST(
    new Request("http://localhost/api/v1/organizations/org/imports/", {
      method: "POST",
      body: "x".repeat(3 * 1024 * 1024 + 1),
    }),
    { params: Promise.resolve({ path: ["organizations", "org", "imports"] }) },
  );
  expect(huge.status).toBe(413);
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("streams authorized source bytes and preserves safe attachment headers", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(new Uint8Array([0, 1, 255]), {
        headers: {
          "Content-Type": "application/octet-stream",
          "Content-Disposition": 'attachment; filename="source.csv"',
          "X-Content-Type-Options": "nosniff",
        },
      }),
    ),
  );
  const result = await GET(
    new Request("http://localhost/api/v1/organizations/org/imports/job/file/"),
    {
      params: Promise.resolve({
        path: ["organizations", "org", "imports", "job", "file"],
      }),
    },
  );
  expect([...new Uint8Array(await result.arrayBuffer())]).toEqual([0, 1, 255]);
  expect(result.headers.get("content-disposition")).toContain("attachment");
  expect(result.headers.get("x-content-type-options")).toBe("nosniff");
  expect(result.headers.get("cache-control")).toContain("no-store");
});

it("submits versioned review decisions to a nested tenant scope without verification fields", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ csrfToken: "mask" }))
    .mockResolvedValueOnce(Response.json({ id: "candidate" }));
  vi.stubGlobal("fetch", fetch);
  await ingestion.review("org", "job", "candidate", {
    expected_version: 2,
    decision: "approve",
    reason: "Supplier compared",
    select_value: true,
    value: "1.35",
    unit: "kg",
  });
  expect(fetch.mock.calls[1][0]).toBe(
    "/api/v1/organizations/org/imports/job/candidates/candidate/review/",
  );
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
    expected_version: 2,
    decision: "approve",
    reason: "Supplier compared",
    select_value: true,
    value: "1.35",
    unit: "kg",
  });
});
