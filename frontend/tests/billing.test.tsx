import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { BillingDetails } from "../app/billing/billing";
import { billing, billingStatement, money, type Billing } from "../lib/billing";

afterEach(() => vi.unstubAllGlobals());
const empty: Billing = {
  collection_available: false,
  statements: [],
  operations: [],
  unapplied_credit: {},
};
const statement = {
  id: "statement-fixture",
  status: "pending",
  settlement_status: "pending",
  period_start: "2026-10-01T00:00:00Z",
  period_end: "2026-11-01T00:00:00Z",
  currency: "XTS",
  exponent: 0,
  total_minor: "1000",
  original_total_minor: "1000",
  settled_minor: "0",
  remaining_minor: "1000",
  snapshot: {},
  mode: "test" as const,
  access_fulfilled: false,
  corrections: [],
  settlements: [],
  download_path: "/api/v1/organizations/org/billing/statements/id/download/",
};

it("formats exact minor units without assuming two decimals or converting through floating point", () => {
  expect(money("123", "JPY", 0)).toBe("JPY 123");
  expect(money("123", "KWD", 3)).toBe("KWD 0.123");
  expect(money("9007199254740993", "USD", 2)).toBe("USD 90071992547409.93");
  expect(money("-5", "USD", 2)).toBe("USD -0.05");
  expect(money("NaN", "USD", 2)).toBe("Amount unavailable");
});
it("renders honest unavailable collection and empty history without a payment action", () => {
  const html = renderToStaticMarkup(<BillingDetails data={empty} />);
  expect(html).toContain("Payment collection is not available");
  expect(html).toContain("No statements yet");
  expect(html).toContain("not tax invoices");
  expect(html).not.toContain("Pay now");
});
it.each([
  "pending",
  "processing",
  "settled",
  "failed",
  "cancelled",
  "expired",
  "partially_settled",
  "action_required",
])("shows %s status without implying access fulfillment", (status) => {
  const html = renderToStaticMarkup(
    <BillingDetails
      data={{
        ...empty,
        statements: [{ ...statement, status }],
        operations: [
          {
            id: "operation-fixture",
            statement_id: statement.id,
            status,
            amount_minor: "1000",
            currency: "XTS",
            expires_at: "2026-10-17T00:00:00Z",
          },
        ],
      }}
    />,
  );
  expect(html).toContain(status.replaceAll("_", " "));
  expect(html).toContain("No change from this statement");
  expect(html).toContain("Download internal statement");
});
it("explains unknown outcomes and unapplied credit", () => {
  const html = renderToStaticMarkup(
    <BillingDetails
      data={{
        ...empty,
        operations: [
          {
            id: "unknown",
            statement_id: statement.id,
            status: "unknown",
            amount_minor: "1000",
            currency: "XTS",
            expires_at: "2026-10-17T00:00:00Z",
          },
        ],
        unapplied_credit: { XTS: "1100" },
      }}
    />,
  );
  expect(html).toContain("do not start a duplicate request");
  expect(html).toContain("1100");
});
it("uses tenant-specific uncached reads and surfaces revoked permission", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json(empty))
    .mockResolvedValueOnce(Response.json(statement))
    .mockResolvedValueOnce(
      Response.json({ detail: "Organization not found." }, { status: 404 }),
    );
  vi.stubGlobal("fetch", fetch);
  await billing("first");
  await billingStatement("first", "statement");
  await expect(billing("second")).rejects.toMatchObject({ status: 404 });
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/organizations/first/billing/");
  expect(fetch.mock.calls[2][0]).toBe("/api/v1/organizations/second/billing/");
  expect(fetch.mock.calls[0][1]).toMatchObject({
    cache: "no-store",
    credentials: "same-origin",
  });
});
