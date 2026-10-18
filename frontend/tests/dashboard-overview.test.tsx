import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import DashboardOverview, { OverviewDetails } from "../app/dashboard/overview";
import { ApiError } from "../lib/api";
import {
  dashboard,
  loadDashboardResource,
  type Dashboard,
  type DashboardResource,
} from "../lib/dashboard";
import type { Commercial } from "../lib/commercial";
import type { Integrations } from "../lib/integrations";

vi.mock("../app/products/ui", () => ({
  useTenant: () => ({
    id: "membership-one",
    role: "owner",
    organization: { id: "org-one", is_active: true },
  }),
  messageFor: (error: unknown) =>
    error instanceof Error ? error.message : "Connection failed. Please retry.",
}));

const scope = "org-one:owner";
const loading = { scope, status: "loading" } as const;
const data: Dashboard = {
  generated_at: "2026-10-18T12:00:00Z",
  scope: "all_time",
  organization: { id: "org-one", name: "One", slug: "one", is_active: true },
  role: "owner",
  products: { total: 31, active: 29, archived: 2 },
  imports: {
    total: 42,
    by_status: { failed: 2, completed_with_errors: 1 },
    awaiting_review: 3,
    attention: 6,
    recent: [
      {
        id: "import-one",
        display_name: "supplier.csv",
        status: "awaiting_review",
        created_at: "2026-10-18T11:00:00Z",
      },
    ],
  },
  equipment: {
    total: 12,
    active: 8,
    draft: 3,
    archived: 1,
    active_with_activated_rules: 7,
  },
  assessments: {
    total: 51,
    compatible: 30,
    incompatible: 15,
    indeterminate: 6,
    recent: [
      {
        id: "assessment-one",
        product_id: "product-one",
        equipment_id: "equipment-one",
        overall: "compatible",
        summary: "Recorded inputs meet configured rules",
        created_at: "2026-10-18T11:30:00Z",
      },
    ],
  },
};

function markup(
  value = data,
  plan: DashboardResource<Commercial> = loading,
  delivery: DashboardResource<Integrations> = loading,
) {
  return renderToStaticMarkup(
    <OverviewDetails
      data={value}
      plan={plan}
      delivery={delivery}
      refreshPlan={() => {}}
      refreshDelivery={() => {}}
    />,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("organization overview", () => {
  it("renders authoritative totals independently of bounded recent rows with scope and actual record links", () => {
    const html = markup();
    expect(html).toContain("<strong>31</strong> total products");
    expect(html).toContain("29 active · 2 archived");
    expect(html).toContain("<strong>6</strong> imports needing attention");
    expect(html).toContain("42 total imports, all statuses");
    expect(html).toContain("<strong>51</strong> assessments, all time");
    expect(html).toContain("7 active profiles with activated rules");
    expect(html).toContain("All-time totals");
    expect(html).toContain('dateTime="2026-10-18T12:00:00Z"');
    expect(html).toContain('href="/organizations/org-one/imports/import-one"');
    expect(html).toContain(
      'href="/organizations/org-one/assessments/assessment-one"',
    );
    expect(html).toContain('href="/organizations/org-one/products/new"');
    expect(html).toContain("Configure equipment");
  });

  it("keeps optional failures and loading separate from successful core data and gives independent retry controls", () => {
    const html = markup(data, {
      scope,
      status: "error",
      error: "Plan details could not be loaded.",
    });
    expect(html).toContain("31</strong> total products");
    expect(html).toContain("Unavailable: Plan details could not be loaded.");
    expect(html).toContain("Retry plan and usage");
    expect(html).toContain("Loading integration deliveries…");
    expect(html).not.toContain("No plan assigned");
    expect(html).not.toContain("No deliveries in the available history");
  });

  it("hides privileged information and actions from members while preserving supported member actions", () => {
    const html = markup({ ...data, role: "member" });
    expect(html).toContain("Add product");
    expect(html).toContain("Upload evidence");
    expect(html).toContain("Run assessment");
    expect(html).not.toContain("Configure equipment");
    expect(html).not.toContain("Plan and usage");
    expect(html).not.toContain("Integration deliveries");
  });

  it("shows genuine empty states and zero counts without fabricating activity", () => {
    const html = markup({
      ...data,
      products: { total: 0, active: 0, archived: 0 },
      imports: {
        total: 0,
        by_status: {},
        awaiting_review: 0,
        attention: 0,
        recent: [],
      },
      assessments: {
        total: 0,
        compatible: 0,
        incompatible: 0,
        indeterminate: 0,
        recent: [],
      },
    });
    expect(html).toContain("<strong>0</strong> total products");
    expect(html).toContain("No imports yet");
    expect(html).toContain("No assessments yet");
    expect(html).not.toContain("supplier.csv");
  });

  it("preserves history when access is expired and does not offer unavailable new-work shortcuts", () => {
    const meter = {
      definition: "Recorded usage",
      limit: 0,
      remaining: 0,
      used: 2,
      reserved: 0,
    };
    const html = markup(data, {
      scope,
      status: "ready",
      data: {
        status: "expired",
        plan: null,
        starts_at: null,
        ends_at: null,
        period_start: "2026-10-01T00:00:00Z",
        period_end: "2026-11-01T00:00:00Z",
        metering_started_at: null,
        historical_usage_complete: false,
        meters: {
          active_products: meter,
          assessments: meter,
          extractions: meter,
        },
        history: [],
      },
    });
    expect(html).toContain("New work is unavailable");
    expect(html).toContain("Earlier usage is incomplete");
    expect(html).toContain("No payments are collected here");
    expect(html).toContain("View assessment history");
    expect(html).not.toContain("Add product");
    expect(html).not.toContain("Run assessment");
  });

  it("labels integration attention as a bounded recent sample rather than an all-time total", () => {
    const html = markup(data, loading, {
      scope,
      status: "ready",
      data: {
        outbound_available: false,
        credential_creation_available: false,
        allowances: { credentials: 0, destinations: 0 },
        credentials: [],
        destinations: [],
        deliveries: ["delivered", "retryable", "terminal", "paused"].map(
          (state) => ({
            id: state,
            event_id: "event",
            destination_id: "destination",
            revision: 1,
            state,
            attempts: 1,
            diagnostic: "",
            status_code: null,
            replays: 0,
            due_at: "2026-10-18T12:00:00Z",
          }),
        ),
      },
    });
    expect(html).toContain(
      "3 need attention among the 4 latest deliveries returned (maximum 100)",
    );
    expect(html).toContain("Outbound delivery is currently unavailable");
  });

  it("initially renders loading rather than zero totals", () => {
    const html = renderToStaticMarkup(<DashboardOverview org="org-one" />);
    expect(html).toContain("Loading organization overview…");
    expect(html).not.toContain("total products");
  });

  it("encodes workspace identifiers, avoids caching, and preserves revoked-access errors", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(Response.json(data))
      .mockResolvedValueOnce(
        Response.json({ detail: "Organization not found." }, { status: 404 }),
      );
    vi.stubGlobal("fetch", fetch);
    await dashboard("org / one");
    await expect(dashboard("org-two")).rejects.toMatchObject({ status: 404 });
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/v1/organizations/org%20%2F%20one/dashboard/",
    );
    expect(fetch.mock.calls[0][1]).toMatchObject({
      cache: "no-store",
      credentials: "same-origin",
    });
    expect(fetch.mock.calls[1][0]).toBe(
      "/api/v1/organizations/org-two/dashboard/",
    );
  });

  it("ignores a slow previous workspace response and a cancelled failure after navigation", async () => {
    let complete!: (data: Dashboard) => void;
    let fail!: (error: Error) => void;
    const publish = vi.fn();
    const old = loadDashboardResource(
      "old:owner",
      () => new Promise<Dashboard>((resolve) => (complete = resolve)),
      publish,
      String,
    );
    const denied = loadDashboardResource(
      "denied:owner",
      () => new Promise<Dashboard>((_, reject) => (fail = reject)),
      publish,
      String,
    );
    await Promise.resolve();
    old.cancel();
    denied.cancel();
    const current = loadDashboardResource(
      "current:member",
      async () => ({ ...data, role: "member" }),
      publish,
      String,
    );
    await current.done;
    complete(data);
    fail(new ApiError(404, "Membership removed"));
    await Promise.all([old.done, denied.done]);
    const completed = publish.mock.calls
      .map(([state]) => state)
      .filter((state) => state.status !== "loading");
    expect(completed).toEqual([
      {
        scope: "current:member",
        status: "ready",
        data: { ...data, role: "member" },
      },
    ]);
  });

  it("reports dependency failure instead of zero, then retries without retaining the failed state", async () => {
    const publish = vi.fn();
    const read = vi
      .fn()
      .mockRejectedValueOnce(new Error("Temporarily unavailable"))
      .mockResolvedValueOnce(data);
    const first = loadDashboardResource(scope, read, publish, String);
    await first.done;
    expect(publish).toHaveBeenLastCalledWith({
      scope,
      status: "error",
      error: "Error: Temporarily unavailable",
    });
    first.cancel();
    const retry = loadDashboardResource(scope, read, publish, String);
    expect(publish).toHaveBeenLastCalledWith({ scope, status: "loading" });
    await retry.done;
    expect(publish).toHaveBeenLastCalledWith({ scope, status: "ready", data });
    expect(read).toHaveBeenCalledTimes(2);
  });
});
