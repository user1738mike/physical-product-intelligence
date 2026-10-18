import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { UsageDetails } from "../app/commercial/usage";
import { commercial, type Commercial } from "../lib/commercial";

const meter = {
  definition: "Synthetic meter",
  limit: null,
  used: 0,
  reserved: 0,
  remaining: null,
};
const data: Commercial = {
  status: "active",
  plan: {
    code: "manual-pilot",
    version: 1,
    name: "Manual pilot",
    features: {},
  },
  starts_at: "2026-10-01T00:00:00Z",
  ends_at: null,
  period_start: "2026-10-01T00:00:00Z",
  period_end: "2026-11-01T00:00:00Z",
  metering_started_at: "2026-10-16T00:00:00Z",
  historical_usage_complete: false,
  meters: { active_products: meter, assessments: meter, extractions: meter },
  history: [],
};
afterEach(() => vi.unstubAllGlobals());

it("shows unlimited allowances, metering start and the manual access boundary", () => {
  const html = renderToStaticMarkup(<UsageDetails data={data} />);
  expect(html).toContain("Unlimited");
  expect(html).toContain("Earlier usage is incomplete");
  expect(html).toContain("No payments are collected");
  expect(html).toContain("No assignments yet");
  expect(html).not.toContain("Checkout");
});

it.each(["expired", "suspended", "unassigned"] as const)(
  "explains %s access and zero allowance",
  (status) => {
    const html = renderToStaticMarkup(
      <UsageDetails
        data={{
          ...data,
          status,
          plan: null,
          meters: {
            ...data.meters,
            extractions: { ...meter, limit: 0, remaining: 0 },
          },
        }}
      />,
    );
    expect(html).toContain("New work is unavailable");
    expect(html).toContain("Allowance exhausted");
    expect(html).toContain("No plan assigned");
  },
);

it("keys every read by organization, avoids caching and surfaces revoked access", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json(data))
    .mockResolvedValueOnce(
      Response.json({ detail: "Organization not found." }, { status: 404 }),
    );
  vi.stubGlobal("fetch", fetch);
  await commercial("first");
  await expect(commercial("second")).rejects.toMatchObject({ status: 404 });
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/v1/organizations/first/commercial/",
  );
  expect(fetch.mock.calls[1][0]).toBe(
    "/api/v1/organizations/second/commercial/",
  );
  expect(fetch.mock.calls[0][1]).toMatchObject({
    cache: "no-store",
    credentials: "same-origin",
  });
});
