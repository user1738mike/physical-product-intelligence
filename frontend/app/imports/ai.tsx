"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ingestion,
  importsPath,
  importsApiPath,
  type ImportJob,
  type Candidate,
  type AICapability,
} from "../../lib/ingestion";
import { products, type Product, type Packaging } from "../../lib/products";
import {
  Field,
  MutationForm,
  Pagination,
  text,
  messageFor,
} from "../products/ui";
import type { Page } from "../../lib/api";

export function AIAvailability({ capability }: { capability: AICapability }) {
  return (
    <p className="notice">
      {capability.available
        ? "AI extraction available."
        : `AI extraction unavailable (${capability.reason.replaceAll("_", " ")}). Deterministic parsing and manual review remain available.`}{" "}
      {capability.privacy_notice}
    </p>
  );
}

export function AIExtraction({
  org,
  job,
  reviewer,
  reload,
}: {
  org: string;
  job: ImportJob;
  reviewer: boolean;
  reload: () => void;
}) {
  const [capability, setCapability] = useState<AICapability | null>(null),
    [error, setError] = useState("");
  const [result, setResult] = useState<Page<Product> | null>(null),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(1);
  const [productId, setProductId] = useState(""),
    [packages, setPackages] = useState<Packaging[]>([]);
  const [requestId] = useState(() => crypto.randomUUID());
  useEffect(() => {
    let live = true;
    void ingestion
      .aiCapability(org)
      .then((c) => {
        if (live) setCapability(c);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org]);
  useEffect(() => {
    let live = true;
    if (reviewer && job.mode !== "ai" && capability?.available)
      void products
        .list(org, { search, page, status: "active", ordering: "sku" })
        .then((r) => {
          if (live) setResult(r);
        })
        .catch((e) => {
          if (live) setError(messageFor(e));
        });
    return () => {
      live = false;
    };
  }, [org, reviewer, job.mode, capability, page, search]);
  useEffect(() => {
    let live = true;
    async function load() {
      const rows: Packaging[] = [];
      if (productId) {
        let page = 1;
        while (true) {
          const r = await products.packaging(org, productId, page);
          rows.push(...r.results);
          if (!r.next) break;
          page++;
        }
      }
      if (live) setPackages(rows.filter((p) => p.is_active));
    }
    void load().catch((e) => {
      if (live) setError(messageFor(e));
    });
    return () => {
      live = false;
    };
  }, [org, productId]);
  return (
    <section className="catalog-panel">
      <h2>
        {job.mode === "ai"
          ? "AI extraction processing"
          : "Extract specifications with AI"}
      </h2>
      {error && <p role="alert">{error}</p>}
      {capability ? (
        <AIAvailability capability={capability} />
      ) : (
        <p role="status">Checking AI availability…</p>
      )}
      {job.mode === "ai" ? (
        <>
          <p>
            Provider {job.extraction?.provider} · Model{" "}
            {job.extraction?.model || "unconfigured"} · Schema{" "}
            {job.extraction?.schema_version} · Attempts{" "}
            {job.extraction?.attempts ?? 0}/3.
          </p>
          <p>
            AI candidates require individual review. Approval accepts a
            documented assertion; it cannot verify a physical measurement,
            modify rules or rewrite assessments.
          </p>
          {job.source_job_id && (
            <Link href={`${importsPath(org)}/${job.source_job_id}`}>
              Original authorized source and deterministic import
            </Link>
          )}
          {reviewer &&
            capability?.available &&
            (job.status === "uploaded" ||
              (job.status === "failed" && job.extraction?.retryable) ||
              job.status === "processing") && (
              <MutationForm
                label={
                  job.status === "failed"
                    ? "Retry eligible AI extraction"
                    : job.status === "processing"
                      ? "Check or recover processing lease"
                      : "Run AI extraction — sends source text"
                }
                action={async () => {
                  await ingestion.action(org, job.id, "ai-process", {
                    expected_version: job.version,
                  });
                  reload();
                }}
              >
                <p>
                  One bounded request, no automatic retry. A processing lease
                  can be recovered after 90 seconds if interrupted. Cancellation
                  discards any late response.
                </p>
              </MutationForm>
            )}
        </>
      ) : reviewer && capability?.available ? (
        <>
          <MutationForm
            label="Search extraction targets"
            action={async (data) => {
              setSearch(text(data, "search"));
              setPage(1);
            }}
          >
            <Field label="Target SKU or name" name="search" />
          </MutationForm>
          {result && (
            <>
              <ul className="record-list">
                {result.results.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      aria-pressed={productId === p.id}
                      onClick={() => setProductId(p.id)}
                    >
                      {p.sku} · {p.name}
                      {productId === p.id ? " · selected" : ""}
                    </button>
                  </li>
                ))}
              </ul>
              <Pagination
                page={page}
                count={result.count}
                hasNext={!!result.next}
                change={setPage}
              />
            </>
          )}
          {productId && (
            <MutationForm
              key={productId}
              label="Queue extraction for selected target"
              action={async (data) => {
                const created = await ingestion.startExtraction(org, job.id, {
                  request_id: requestId,
                  product_id: productId,
                  packaging_id: text(data, "packaging_id") || null,
                });
                window.location.assign(`${importsPath(org)}/${created.id}`);
              }}
            >
              <label className="field">
                Target packaging scope
                <select name="packaging_id">
                  <option value="">Product-level attributes</option>
                  {packages.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {p.level}
                    </option>
                  ))}
                </select>
              </label>
              <p>
                Confirm this document describes the selected product and
                package. Only its bounded source text is sent when you
                explicitly run the queued extraction. Existing values remain
                unchanged until review and application. Textual identity fields
                always apply to the product.
              </p>
            </MutationForm>
          )}
        </>
      ) : reviewer ? null : (
        <p>
          Owner/admin permission is required to request AI extraction or approve
          candidates.
        </p>
      )}
    </section>
  );
}

export function AICandidateProvenance({
  org,
  candidate: c,
}: {
  org: string;
  candidate: Candidate;
}) {
  if (!c.extraction?.method) return null;
  return (
    <aside className="notice">
      <p>
        AI-extracted candidate · {c.extraction.provider} / {c.extraction.model}{" "}
        · {c.extraction.schema_version} · {c.extraction.extracted_at}
      </p>
      <p>
        Validation: {c.extraction.validation}.{" "}
        {c.extraction.grounded
          ? "Exact source excerpt mapped; meaning still requires human review."
          : "Source location unavailable or grounding invalid. This candidate cannot be approved."}{" "}
        Approval is not physical verification.
      </p>
      <blockquote>
        {c.extraction.quote || "No validated source excerpt available."}
      </blockquote>
      <a href={`${importsApiPath(org)}${c.extraction.source_job_id}/file/`}>
        Inspect authorized private source
      </a>
    </aside>
  );
}
