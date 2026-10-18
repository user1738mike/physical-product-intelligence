import { afterEach, expect, it, vi } from "vitest";
import {
  createCredential,
  integrations,
  replayDelivery,
  revokeCredential,
  rotateSigning,
  saveDestination,
  scopes,
} from "../lib/integrations";

afterEach(() => vi.unstubAllGlobals());

it("uses explicit read-only scopes and tenant-specific uncached management reads", async () => {
  expect(scopes).toEqual([
    "catalog:read",
    "assessments:read",
    "assessments:export",
  ]);
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ credentials: [] }))
    .mockResolvedValueOnce(
      Response.json({ detail: "Organization not found." }, { status: 404 }),
    );
  vi.stubGlobal("fetch", fetch);
  await integrations("first");
  await expect(integrations("second")).rejects.toMatchObject({ status: 404 });
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/v1/organizations/first/integrations/",
  );
  expect(fetch.mock.calls[1][0]).toBe(
    "/api/v1/organizations/second/integrations/",
  );
  expect(fetch.mock.calls[0][1]).toMatchObject({
    cache: "no-store",
    credentials: "same-origin",
  });
});

it("protects reveal-once creation and revocation with existing CSRF session transport", async () => {
  const fetch = vi
    .fn()
    .mockImplementation(async (url: string) =>
      url.endsWith("/csrf/")
        ? Response.json({ csrfToken: "synthetic-csrf" })
        : Response.json({ id: "fixture", secret: "synthetic-transient-only" }),
    );
  vi.stubGlobal("fetch", fetch);
  const value = await createCredential("org", {
    name: "Warehouse",
    scopes: ["catalog:read"],
    expires_at: "2026-11-01T00:00:00Z",
  });
  expect(value.secret).toBe("synthetic-transient-only");
  await revokeCredential("org", "fixture");
  const mutations = fetch.mock.calls.filter(
    (call) => call[1]?.method === "POST",
  );
  expect(mutations).toHaveLength(2);
  expect(new Headers(mutations[0][1].headers).get("X-CSRFToken")).toBe(
    "synthetic-csrf",
  );
  expect(mutations[0][0]).not.toContain(value.secret);
});

it("sends destination revisions and explicit compromised-key rotation", async () => {
  const fetch = vi
    .fn()
    .mockImplementation(async (url: string) =>
      url.endsWith("/csrf/")
        ? Response.json({ csrfToken: "synthetic-csrf" })
        : Response.json({ id: "destination" }),
    );
  vi.stubGlobal("fetch", fetch);
  await saveDestination(
    "org",
    {
      url: "https://warehouse.example/events",
      subscriptions: [],
      enabled: false,
      expected_revision: 3,
    },
    "destination",
  );
  await rotateSigning("org", "destination", true);
  const patch = fetch.mock.calls.find((call) => call[1]?.method === "PATCH");
  expect(JSON.parse(patch![1].body)).toMatchObject({
    enabled: false,
    expected_revision: 3,
  });
  const rotate = fetch.mock.calls.find((call) => call[0].endsWith("/rotate/"));
  expect(JSON.parse(rotate![1].body)).toEqual({ immediate: true });
});

it("surfaces bounded replay denials without a success claim", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(async (url: string) =>
        url.endsWith("/csrf/")
          ? Response.json({ csrfToken: "synthetic-csrf" })
          : Response.json(
              { detail: "This delivery cannot be replayed." },
              { status: 400 },
            ),
      ),
  );
  await expect(replayDelivery("org", "delivery")).rejects.toMatchObject({
    status: 400,
  });
});
