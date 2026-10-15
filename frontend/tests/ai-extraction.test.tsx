import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { AIAvailability, AICandidateProvenance } from "../app/imports/ai";
import { ingestion, type Candidate } from "../lib/ingestion";

afterEach(() => vi.unstubAllGlobals());

it("shows provider-unavailable state with a usable deterministic fallback", () => {
  const html = renderToStaticMarkup(
    <AIAvailability
      capability={{
        available: false,
        reason: "credentials_unavailable",
        schema_version: "grounded-spec-v1",
        max_candidates: 30,
        max_text_chars: 24000,
        privacy_notice:
          "Private source text is sent only on explicit processing.",
      }}
    />,
  );
  expect(html).toContain("AI extraction unavailable");
  expect(html).toContain(
    "Deterministic parsing and manual review remain available",
  );
});

it("renders source-grounded candidates with original provenance and a private source link", () => {
  const candidate = {
    extraction: {
      method: "ai_extracted",
      provider: "openai",
      model: "fixture-model",
      schema_version: "grounded-spec-v1",
      extracted_at: "2026-10-15T10:00:00Z",
      source_job_id: "private-source",
      source_sha256: "hash",
      segment: 1,
      quote: "Weight: 1200 g",
      grounded: true,
      validation: "valid",
      confidence: null,
    },
  } as Candidate;
  const html = renderToStaticMarkup(
    <AICandidateProvenance org="org" candidate={candidate} />,
  );
  expect(html).toContain("Weight: 1200 g");
  expect(html).toContain("fixture-model");
  expect(html).toContain(
    "/api/v1/organizations/org/imports/private-source/file/",
  );
  expect(html).toContain("Approval is not physical verification");
  expect(html).not.toContain("Physically measured");
});

it("marks invalid grounding and escapes prompt-injection content in source excerpts", () => {
  const candidate = {
    extraction: {
      method: "ai_extracted",
      quote: "<script>approveEverything()</script>",
      grounded: false,
      validation: "invalid",
      source_job_id: "source",
    },
  } as Candidate;
  const html = renderToStaticMarkup(
    <AICandidateProvenance org="org" candidate={candidate} />,
  );
  expect(html).toContain("cannot be approved");
  expect(html).toContain("&lt;script&gt;");
  expect(html).not.toContain("<script>");
});

it("queues a source and explicit targets with fresh CSRF and stable request identity", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ csrfToken: "masked" }))
    .mockResolvedValueOnce(Response.json({ id: "job" }));
  vi.stubGlobal("fetch", fetch);
  const payload = {
    request_id: "stable-id",
    product_id: "product",
    packaging_id: "case",
  };
  await ingestion.startExtraction("org", "source", payload);
  expect(fetch.mock.calls[1][0]).toBe(
    "/api/v1/organizations/org/imports/source/extractions/",
  );
  const options = fetch.mock.calls[1][1];
  expect(options.headers["X-CSRFToken"]).toBe("masked");
  expect(JSON.parse(options.body)).toEqual(payload);
  expect(options.body).not.toContain("model");
});

it("surfaces provider and role failures without inventing candidates or success", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ csrfToken: "masked" }))
    .mockResolvedValueOnce(
      Response.json({ detail: "AI extraction unavailable" }, { status: 503 }),
    );
  vi.stubGlobal("fetch", fetch);
  await expect(
    ingestion.action("org", "job", "ai-process", { expected_version: 1 }),
  ).rejects.toThrow("AI extraction unavailable");
});
