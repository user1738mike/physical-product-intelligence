import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import {
  AssessmentResult,
  constraintDescription,
} from "../app/compatibility/assessments";
import { rulePayload } from "../app/compatibility/equipment";
import {
  compatibility,
  type Assessment,
  type EquipmentDefinition,
  type Rule,
} from "../lib/compatibility";
import type { Claim } from "../lib/products";

afterEach(() => vi.unstubAllGlobals());
it("explains retained effective limits without inventing missing operands", () => {
  const rule = {
    type: "maximum",
    expected: {
      limit: "10",
      unit: "cm",
      margin: "1",
      effective_limit: "90",
      canonical_unit: "mm",
    },
  } as unknown as import("../lib/compatibility").RuleResult;
  expect(constraintDescription(rule)).toContain(
    "inclusive effective limit 90 mm",
  );
  expect(
    constraintDescription({ ...rule, expected: { limit: "10", unit: "cm" } }),
  ).toContain("effective limit unknown");
});
const definition: EquipmentDefinition = {
  name: "Conveyor fixture",
  description: "Static envelope",
  manufacturer: "Unknown",
  model: "",
  category: "conveyor",
  source_reference: "Manual 2",
  operational_context: "Case handling",
  supported_levels: ["case"],
  orientation_notes: "",
  handling_notes: "",
};
const source = {
  id: "source",
  product_id: "product",
  title: "Supplier claim",
  source_type: "supplier_document" as const,
  source_reference: "Manual fixture",
  description: "",
  declared_sha256: "",
  capture_status: "reference_only" as const,
  attribution: "Fixture",
  license: "Unknown",
  observed_at: "2026-10-01T00:00:00Z",
  recorded_at: "2026-10-01T00:00:00Z",
  recorded_by_id: 1,
};
const claim: Claim = {
  id: "claim",
  product_id: "product",
  packaging_id: null,
  attribute: "mass",
  basis: "estimated",
  value: "1",
  unit: "kg",
  lower: null,
  upper: null,
  canonical_value: "1",
  canonical_unit: "kg",
  canonical_lower: null,
  canonical_upper: null,
  conversion_version: "metric-v1",
  text_value: "",
  method: "External estimate fixture",
  limitations: "No physical observation",
  observed_at: source.observed_at,
  recorded_at: source.recorded_at,
  recorded_by_id: 1,
  evidence: source,
  verification_record: null,
  verifications: [],
};
const snapshot: Assessment = {
  id: "assessment",
  organization_id: "org",
  request_id: "request",
  product_id: "product",
  product_revision_id: "revision",
  packaging_id: null,
  packaging_revision_id: null,
  equipment_id: "equipment",
  equipment_revision_id: "equipment-revision",
  rule_set_id: "rules",
  parent_id: null,
  created_at: "2026-10-15T10:00:00Z",
  created_by_id: 1,
  engine_version: "warehouse-fit-v1",
  overall: "indeterminate",
  summary: "Missing or conflicting inputs prevent a justified result.",
  inputs: {
    product: {
      id: "product",
      sku: "TEST-1",
      name: "Carton",
      latest_revision_number: 2,
    },
    packaging: null,
    orientation: null,
    handling_level: null,
    level_basis: "unknown",
    attributes: {
      mass: {
        claims: [claim],
        conflicting: true,
        quality_status: "conflict",
        selected_claim_id: null,
        selection: null,
      },
      length: {
        claims: [],
        conflicting: false,
        quality_status: "unknown",
        selected_claim_id: null,
        selection: null,
      },
    },
  },
  equipment_snapshot: { id: "equipment-revision", number: 3, definition },
  rule_snapshot: {
    id: "rules",
    equipment_id: "equipment",
    equipment_revision_id: "equipment-revision",
    number: 4,
    name: "Limits",
    rules: [],
    evidence_policy: "measured_only",
    schema_version: "warehouse-rules-v1",
    reason: "Fixture",
    created_at: "2026-10-15T00:00:00Z",
    created_by_id: 1,
    activation: null,
  },
  results: [
    {
      rule_id: "limit-mass",
      rule_version: 4,
      rule_set_version: 4,
      name: "Maximum mass",
      type: "maximum",
      severity: "hard",
      attribute: "mass",
      status: "indeterminate",
      reason: "No qualifying measured input.",
      used_claim_ids: [],
      recorded_values: [claim],
      expected: { limit: "2", unit: "kg", margin: "0", boundary: "inclusive" },
    },
  ],
};

it("renders unknown and conflicting evidence without promoting an estimate", () => {
  const html = renderToStaticMarkup(
    <AssessmentResult org="org" assessment={snapshot} />,
  );
  expect(html).toContain("Assessment: indeterminate");
  expect(html).toContain("Conflicting claims");
  expect(html).toContain("Missing / unknown");
  expect(html).toContain("Estimated — not verified");
  expect(html).toContain("specification 3");
  expect(html).toContain("rule-set 4");
  expect(html).toContain("not physical validation");
  expect(html).not.toContain("Physically measured (attested)");
});

it("keeps compatibility explicitly conditional and escapes untrusted rule text", () => {
  const a = {
    ...snapshot,
    overall: "compatible" as const,
    results: [
      {
        ...snapshot.results[0],
        name: "<script>unsafe()</script>",
        status: "pass" as const,
      },
    ],
  };
  const html = renderToStaticMarkup(
    <AssessmentResult org="org" assessment={a} />,
  );
  expect(html).toContain("Assessment: compatible");
  expect(html).toContain("not physical validation");
  expect(html).toContain("&lt;script&gt;");
  expect(html).not.toContain("<script>unsafe");
});

it("sends a stable idempotency key with explicit scope and fresh CSRF", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ csrfToken: "mask" }))
    .mockResolvedValueOnce(Response.json(snapshot));
  vi.stubGlobal("fetch", fetch);
  const data = {
    request_id: "stable-request",
    product_id: "product",
    equipment_id: "equipment",
    packaging_id: null,
    rule_set_id: "rules",
    orientation: "as_recorded",
    product_level: "case",
  };
  await compatibility.assess("org", data);
  expect(fetch.mock.calls[1][0]).toBe("/api/v1/organizations/org/assessments/");
  expect(fetch.mock.calls[1][1].headers["X-CSRFToken"]).toBe("mask");
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual(data);
  expect(JSON.parse(fetch.mock.calls[1][1].body)).not.toHaveProperty(
    "actor_id",
  );
});

it("reports API validation and permission failures rather than fabricating results", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ csrfToken: "mask" }))
    .mockResolvedValueOnce(
      Response.json(
        { detail: "Only activated rule sets can run." },
        { status: 400 },
      ),
    );
  vi.stubGlobal("fetch", fetch);
  await expect(compatibility.assess("org", {})).rejects.toThrow(
    "Only activated rule sets can run.",
  );
});

it("filters immutable history in the query and strips derived rule fields from revisions", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      Response.json({ results: [], count: 0, next: null, previous: null }),
    );
  vi.stubGlobal("fetch", fetch);
  await compatibility.assessments("org", {
    product_id: "product",
    equipment_id: "equipment",
    overall: "indeterminate",
    date_from: "2026-10-01T00:00:00Z",
    page: 2,
  });
  const url = new URL(fetch.mock.calls[0][0], "http://localhost");
  expect(url.searchParams.get("overall")).toBe("indeterminate");
  expect(url.searchParams.get("page")).toBe("2");
  const rule: Rule = {
    id: "rule",
    type: "maximum",
    name: "Limit",
    explanation: "Documented limit",
    severity: "hard",
    enabled: true,
    attribute: "mass",
    limit: "2",
    unit: "kg",
    margin: "0",
    source_reference: "Manual",
    source: { kind: "import", id: "job", snapshot: { private: "metadata" } },
    version: 2,
    canonical_limit: "2",
  };
  const payload = rulePayload(rule);
  expect(payload).not.toHaveProperty("version");
  expect(payload).not.toHaveProperty("canonical_limit");
  expect(payload.source).toEqual({ kind: "import", id: "job" });
});
