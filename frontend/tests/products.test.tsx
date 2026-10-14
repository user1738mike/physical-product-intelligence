import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AttributeSummary,
  ClaimCard,
  ClaimForm,
} from "../app/products/evidence";
import { products, type AttributeState, type Claim } from "../lib/products";
import { request } from "../lib/api";

const source = {
  title: "Supplier fixture",
  source_type: "supplier_document" as const,
  source_reference: "Catalog revision 7",
  attribution: "Fixture supplier",
  license: "Not confirmed",
  observed_at: "2026-01-01T10:00:00Z",
};
const claim: Claim = {
  id: "claim-fixture",
  product_id: "product-fixture",
  packaging_id: null,
  attribute: "mass",
  basis: "estimated",
  value: "1250.000000",
  unit: "g",
  lower: null,
  upper: null,
  canonical_value: "1.250000000",
  canonical_unit: "kg",
  canonical_lower: null,
  canonical_upper: null,
  text_value: "",
  conversion_version: "metric-v1",
  method: "Fixture model version 1",
  limitations: "No physical sample",
  observed_at: "2026-01-01T10:00:00Z",
  recorded_at: "2026-01-01T12:00:00Z",
  recorded_by_id: 1,
  evidence: {
    ...source,
    id: "evidence-fixture",
    product_id: "product-fixture",
    capture_status: "reference_only",
    declared_sha256: "",
    recorded_at: "2026-01-01T12:00:00Z",
    recorded_by_id: 1,
  },
  verification_record: null,
  verifications: [],
};
afterEach(() => vi.unstubAllGlobals());

describe("catalog workflow boundary", () => {
  it("keeps search text in query parameters and rejects traversal paths", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        Response.json({ count: 0, next: null, previous: null, results: [] }),
      );
    vi.stubGlobal("fetch", fetch);
    await products.list("tenant", {
      search: "SKU..01 & / supplier",
      page: 2,
      ordering: "sku",
    });
    const target = new URL(fetch.mock.calls[0][0], "http://localhost");
    expect(target.pathname).toBe("/api/v1/organizations/tenant/products/");
    expect(target.searchParams.get("search")).toBe("SKU..01 & / supplier");
    expect(target.searchParams.get("page")).toBe("2");
    await expect(request("/api/v1/../admin/")).rejects.toThrow(
      "Unsupported API path",
    );
  });

  it("sends versioned edits with fresh CSRF and no ownership fields", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(Response.json({ csrfToken: "fixture-mask" }))
      .mockResolvedValueOnce(Response.json({ id: "product" }));
    vi.stubGlobal("fetch", fetch);
    await products.edit(
      "tenant",
      "product",
      {
        name: "Changed",
        brand: "",
        manufacturer: "",
        model_number: "",
        category: "",
        description: "",
      },
      3,
      "Correct description",
    );
    const options = fetch.mock.calls[1][1];
    expect(options.method).toBe("PATCH");
    expect(options.headers["X-CSRFToken"]).toBe("fixture-mask");
    expect(JSON.parse(options.body)).toMatchObject({
      expected_revision: 3,
      change_reason: "Correct description",
    });
    expect(JSON.parse(options.body)).not.toHaveProperty("organization_id");
    expect(options.credentials).toBe("same-origin");
  });

  it("submits an estimate and its source atomically without a verified status", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(Response.json({ csrfToken: "fixture-mask" }))
      .mockResolvedValueOnce(Response.json(claim));
    vi.stubGlobal("fetch", fetch);
    await products.addClaim(
      "tenant",
      "product",
      {
        attribute: "mass",
        basis: "estimated",
        value: "1250",
        unit: "g",
        method: "Model v1",
        limitations: "No sample",
        observed_at: source.observed_at,
        source,
      },
      "packaging",
    );
    expect(fetch.mock.calls[1][0]).toBe(
      "/api/v1/organizations/tenant/products/product/packaging/packaging/claims/",
    );
    const payload = JSON.parse(fetch.mock.calls[1][1].body);
    expect(payload.source.source_reference).toBe("Catalog revision 7");
    expect(payload.basis).toBe("estimated");
    expect(payload).not.toHaveProperty("verified_by_id");
  });

  it("preserves structured validation errors for nested measurements", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(Response.json({ csrfToken: "fixture-mask" }))
        .mockResolvedValueOnce(
          Response.json(
            {
              source: {
                observed_at: ["Observation time cannot be in the future."],
              },
            },
            { status: 400 },
          ),
        ),
    );
    await expect(
      request("/api/v1/organizations/tenant/products/", "POST", {}),
    ).rejects.toMatchObject({
      status: 400,
      message: "Observation time cannot be in the future.",
    });
  });

  it("renders estimates and physical attestation distinctly and hides privileged controls from members", () => {
    const markup = renderToStaticMarkup(
      <ClaimCard
        claim={claim}
        org="tenant"
        product="product"
        privileged={false}
        writable
        saved={() => {}}
      />,
    );
    expect(markup).toContain("Estimated — not verified");
    expect(markup).toContain("No physical sample");
    expect(markup).toContain("Catalog revision 7");
    expect(markup).toContain("1250.000000 g");
    expect(markup).not.toContain("Record physical verification");
    expect(markup).not.toContain("Select claim with rationale");
    const verified = {
      ...claim,
      basis: "measured" as const,
      verification_record: {
        id: "verification",
        claim_id: claim.id,
        measured_claim_id: "measurement",
        verified_by_id: 7,
        verified_at: "2026-01-02T10:00:00Z",
        instrument: "Scale fixture",
        procedure: "Weighed the sealed sample",
        notes: "Single sample only",
      },
    };
    const attested = renderToStaticMarkup(
      <ClaimCard
        claim={verified}
        org="tenant"
        product="product"
        privileged={false}
        writable
        saved={() => {}}
      />,
    );
    expect(attested).toContain("Physically verified (attested)");
    expect(attested).toContain("Scale fixture");
    expect(attested).toContain("Single sample only");
  });

  it("shows unknowns and unresolved disagreement without inventing canonical values", () => {
    const states: AttributeState[] = [
      {
        attribute: "mass",
        status: "conflict",
        claim_count: 2,
        conflicting: true,
        selected_claim: null,
        selection: null,
      },
      {
        attribute: "width",
        status: "unknown",
        claim_count: 0,
        conflicting: false,
        selected_claim: null,
        selection: null,
      },
    ];
    const markup = renderToStaticMarkup(<AttributeSummary states={states} />);
    expect(markup).toContain("Unresolved disagreement");
    expect(markup).toContain("No canonical value selected");
    expect(markup).toContain("Unknown");
    expect(markup).not.toContain("0 kg");
  });

  it("renders an accessible claim form with explicit units and source fields", () => {
    const markup = renderToStaticMarkup(
      <ClaimForm org="tenant" product="product" saved={() => {}} />,
    );
    expect(markup).toContain('aria-label="Record attribute claim"');
    expect(markup).toContain("Choose an explicit unit");
    expect(markup).toContain("Source or notebook reference");
    expect(markup).toContain("Manual entry does not verify a physical value");
    expect(markup).not.toContain('value="measured"');
  });
});
