"use client";

import Link from "next/link";
import { AIExtraction, AICandidateProvenance } from "./ai";
import { useEffect, useState } from "react";
import { type Page } from "../../lib/api";
import {
  fields,
  ingestion,
  importsApiPath,
  importsPath,
  type ImportJob,
  type ImportRow,
  type Candidate,
  type ReviewRecord,
} from "../../lib/ingestion";
import {
  Field,
  MutationForm,
  Pagination,
  TenantFrame,
  messageFor,
  text,
  useTenant,
} from "../products/ui";

export function ImportList({ org }: { org: string }) {
  return (
    <TenantFrame org={org}>
      <List org={org} />
    </TenantFrame>
  );
}
function List({ org }: { org: string }) {
  const [jobs, setJobs] = useState<Page<ImportJob> | null>(null);
  const [limits, setLimits] = useState<Record<string, number>>({});
  const [page, setPage] = useState(1),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    void Promise.all([ingestion.jobs(org, page), ingestion.limits(org)])
      .then(([a, b]) => {
        if (live) {
          setJobs(a);
          setLimits(b.limits);
        }
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, page]);
  return (
    <>
      <h1>Evidence imports</h1>
      <p>
        Upload source data, confirm column mappings, and review every catalog
        change before application.
      </p>
      {error && <p role="alert">{error}</p>}
      <section className="catalog-panel">
        <h2>Start an import</h2>
        <p>
          CSV, XLSX, text-based PDF, TXT. Maximum{" "}
          {Math.round((limits.upload_bytes ?? 2097152) / 1024)} KiB,{" "}
          {limits.rows ?? 200} rows, {limits.sheets ?? 5} sheets,{" "}
          {limits.pages ?? 10} PDF pages. No macros, formulas, OCR or inferred
          units. PDF/TXT extraction supports labeled fields such as “SKU: ABC”
          and “Weight: 1.2 kg”.
        </p>
        <MutationForm
          label="Upload source"
          action={async (data) => {
            const file = data.get("file");
            if (!(file instanceof File) || !file.size)
              throw new Error("Choose a file.");
            const job = await ingestion.upload(org, file);
            window.location.assign(`${importsPath(org)}/${job.id}`);
          }}
        >
          <Field
            label="Source file"
            type="file"
            name="file"
            accept=".csv,.xlsx,.pdf,.txt"
            required
          />
        </MutationForm>
      </section>
      <h2>Import jobs</h2>
      {!jobs ? (
        <p role="status">Loading imports…</p>
      ) : (
        <>
          <ul className="record-list">
            {jobs.results.map((job) => (
              <li key={job.id}>
                <Link href={`${importsPath(org)}/${job.id}`}>
                  {job.display_name}
                </Link>{" "}
                · {job.status.replaceAll("_", " ")}
              </li>
            ))}
          </ul>
          {!jobs.count && <p>No imports yet.</p>}
          <Pagination
            page={page}
            count={jobs.count}
            hasNext={!!jobs.next}
            change={setPage}
          />
        </>
      )}
    </>
  );
}

export function ImportDetail({ org, id }: { org: string; id: string }) {
  return (
    <TenantFrame org={org}>
      <Detail org={org} id={id} />
    </TenantFrame>
  );
}
function Detail({ org, id }: { org: string; id: string }) {
  const membership = useTenant(),
    reviewer = membership.role !== "member";
  const [job, setJob] = useState<ImportJob | null>(null),
    [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const reload = () => setRefresh((n) => n + 1);
  useEffect(() => {
    let live = true;
    void ingestion
      .job(org, id)
      .then((j) => {
        if (live) setJob(j);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, id, refresh]);
  if (error) return <p role="alert">{error}</p>;
  if (!job) return <p role="status">Loading import…</p>;
  const terminal = ["completed", "completed_with_errors", "cancelled"].includes(
    job.status,
  );
  const action = async (name: string, data: unknown) => {
    setJob(await ingestion.action(org, id, name, data));
    reload();
  };
  return (
    <>
      <Link href={importsPath(org)}>All imports</Link>
      <h1>{job.display_name}</h1>
      <AIExtraction org={org} job={job} reviewer={reviewer} reload={reload} />
      <section className="catalog-panel">
        <h2>Import status: {job.status.replaceAll("_", " ")}</h2>
        <p>
          Parser {job.parser_version} · Scan: {job.scan_status} · Source SHA-256{" "}
          <code className="import-digest">{job.sha256}</code>
        </p>
        {job.scan_status === "unscanned" && (
          <p className="notice">
            Development upload: malware scanning has not been performed.
          </p>
        )}
        {job.duplicate_upload_ids.length > 0 && (
          <p className="notice">
            Identical bytes were previously uploaded. This job still requires
            independent review; it will not overwrite or apply automatically.
          </p>
        )}
        <dl className="detail-grid">
          {Object.entries(job.counters).map(([key, value]) => (
            <div key={key}>
              <dt>{key.replaceAll("_", " ")}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        {job.errors.map((e, i) => (
          <p key={i} role="alert">
            {e.message}
          </p>
        ))}
        <p>
          <a href={`${importsApiPath(org)}${id}/file/`}>
            Download private source
          </a>{" "}
          ·{" "}
          <a href={`${importsApiPath(org)}${id}/errors/`}>
            Download authorized error report
          </a>
        </p>
        {!terminal && reviewer && (
          <MutationForm
            label="Cancel import"
            action={() => action("cancel", { expected_version: job.version })}
          >
            <p>
              Retain the uploaded source and review history without applying it.
            </p>
          </MutationForm>
        )}
      </section>
      {job.mode !== "ai" && ["uploaded", "failed"].includes(job.status) && (
        <section className="catalog-panel">
          <h2>1. Validate and preview</h2>
          <MutationForm
            label="Validate source"
            action={(data) =>
              action("validate", {
                expected_version: job.version,
                sheet: text(data, "sheet"),
                header_row: Number(text(data, "header_row")),
                delimiter: text(data, "delimiter"),
              })
            }
          >
            {job.format === "xlsx" && (
              <>
                <Field
                  label="Sheet name (blank selects first sheet)"
                  name="sheet"
                  list="sheet-options"
                />
                <datalist id="sheet-options">
                  {job.preview.sheets?.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </datalist>
              </>
            )}
            {["xlsx", "csv"].includes(job.format) && (
              <Field
                label="Header row"
                name="header_row"
                type="number"
                min={1}
                max={20}
                defaultValue="1"
                required
              />
            )}
            {!["xlsx", "csv"].includes(job.format) && (
              <input type="hidden" name="header_row" value="1" />
            )}
            {job.format === "csv" && (
              <label className="field">
                Delimiter
                <select name="delimiter">
                  <option value="">Detect safely</option>
                  <option value=",">Comma</option>
                  <option value=";">Semicolon</option>
                  <option value={"\t"}>Tab</option>
                  <option value="|">Pipe</option>
                </select>
              </label>
            )}
          </MutationForm>
          {job.preview.sample && (
            <div className="table-scroll">
              <table>
                <caption>
                  Source preview · {job.preview.row_count} nonempty rows
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Location</th>
                    {job.preview.headers?.map((h) => (
                      <th scope="col" key={h}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {job.preview.sample.map((row, i) => (
                    <tr key={i}>
                      <th scope="row">{row.location}</th>
                      {job.preview.headers?.map((h) => (
                        <td key={h}>{row.cells[h] || "Unknown"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {job.preview.headers && (
            <>
              <h2>2. Confirm field mapping</h2>
              <p>
                Suggestions require confirmation. Leave unused columns unmapped.
                Units must be explicit in the source.
              </p>
              <MutationForm
                key={job.version}
                label="Save field mapping"
                action={(data) =>
                  action("mapping", {
                    expected_version: job.version,
                    mapping: Object.fromEntries(
                      fields
                        .map((f) => [f, text(data, f)])
                        .filter(([, v]) => v),
                    ),
                  })
                }
              >
                <div className="form-grid">
                  {fields.map((field) => (
                    <label className="field" key={field}>
                      {field.replaceAll("_", " ")}
                      <select
                        name={field}
                        required={field === "sku"}
                        defaultValue={
                          job.mapping[field] ??
                          job.preview.suggestions?.[field] ??
                          ""
                        }
                      >
                        <option value="">Not mapped</option>
                        {job.preview.headers?.map((header) => (
                          <option key={header} value={header}>
                            {header}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              </MutationForm>
              {Object.keys(job.mapping).length > 0 && (
                <MutationForm
                  label="Process candidates"
                  action={() =>
                    action("process", { expected_version: job.version })
                  }
                >
                  <p>
                    Parsing creates review candidates only. No catalog values
                    will change.
                  </p>
                </MutationForm>
              )}
            </>
          )}
        </section>
      )}
      {(job.status === "awaiting_review" || terminal) && (
        <>
          <Rows
            key={`rows-${refresh}`}
            org={org}
            id={id}
            reviewer={reviewer && !terminal}
            reload={reload}
          />
          <Candidates
            key={`candidates-${refresh}`}
            org={org}
            id={id}
            reviewer={reviewer && !terminal}
            reload={reload}
          />
          {job.status === "awaiting_review" && reviewer && (
            <section className="catalog-panel">
              <h2>Apply reviewed changes</h2>
              <p>
                All candidates must be approved or rejected. Application is one
                transaction. Stale catalog data requires a refresh and renewed
                review.
              </p>
              <MutationForm
                label="Apply approved changes"
                action={() =>
                  action("apply", { expected_version: job.version })
                }
              >
                <p>
                  Approved measurements become reported evidence. Only explicit
                  selection changes the canonical measurement.
                </p>
              </MutationForm>
              <MutationForm
                label="Refresh comparisons"
                action={() =>
                  action("refresh", { expected_version: job.version })
                }
              >
                <p>
                  This resets candidate decisions to pending and compares with
                  the latest catalog.
                </p>
              </MutationForm>
            </section>
          )}
        </>
      )}
      <History key={`history-${refresh}`} org={org} id={id} />
    </>
  );
}

function Rows({
  org,
  id,
  reviewer,
  reload,
}: {
  org: string;
  id: string;
  reviewer: boolean;
  reload: () => void;
}) {
  const [result, setResult] = useState<Page<ImportRow> | null>(null),
    [page, setPage] = useState(1),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    void ingestion
      .rows(org, id, page)
      .then((r) => {
        if (live) setResult(r);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, id, page]);
  return (
    <section className="catalog-panel">
      <h2>Row validation and product creation</h2>
      {error && <p role="alert">{error}</p>}
      {result?.results.map((row) => (
        <article className="evidence-card" key={row.id}>
          <h3>
            {row.sku || "Invalid SKU"} · {row.location}
          </h3>
          <p>
            {row.applied
              ? "Applied"
              : row.product_id
                ? "Existing product"
                : "Proposed new product"}
          </p>
          {row.product_id && (
            <Link href={`/organizations/${org}/products/${row.product_id}`}>
              View resulting product
            </Link>
          )}
          {row.errors.map((e, i) => (
            <p key={i} className="notice error">
              {e}
            </p>
          ))}
          {reviewer && !row.product_id && !row.errors.length && (
            <MutationForm
              label={
                row.allow_create
                  ? "Withdraw product creation approval"
                  : "Approve new product creation"
              }
              action={async (data) => {
                await ingestion.creation(
                  org,
                  id,
                  row.id,
                  !row.allow_create,
                  text(data, "reason"),
                );
                reload();
              }}
            >
              <Field
                label="Creation decision reason"
                name="reason"
                minLength={5}
                required
              />
            </MutationForm>
          )}
        </article>
      ))}
      {result && (
        <Pagination
          page={page}
          count={result.count}
          hasNext={!!result.next}
          change={setPage}
        />
      )}
    </section>
  );
}

function Candidates({
  org,
  id,
  reviewer,
  reload,
}: {
  org: string;
  id: string;
  reviewer: boolean;
  reload: () => void;
}) {
  const [result, setResult] = useState<Page<Candidate> | null>(null),
    [page, setPage] = useState(1),
    [decision, setDecision] = useState(""),
    [quality, setQuality] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    void ingestion
      .candidates(org, id, page, decision, quality)
      .then((r) => {
        if (live) setResult(r);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, id, page, decision, quality]);
  return (
    <section className="catalog-panel">
      <h2>Review candidate attributes</h2>
      <p>
        Source assertions are reported, never physically verified by import
        approval. Original values and every review decision remain traceable.
      </p>
      <label className="field">
        Decision filter
        <select
          value={decision}
          onChange={(e) => {
            setDecision(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All decisions</option>
          {["pending", "approve", "reject"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </label>
      <label className="field">
        Quality filter
        <select
          value={quality}
          onChange={(e) => {
            setQuality(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All qualities</option>
          {["new", "equivalent", "duplicate", "conflict", "invalid"].map(
            (v) => (
              <option key={v}>{v}</option>
            ),
          )}
        </select>
      </label>
      {error && <p role="alert">{error}</p>}
      {result?.results.map((c) => (
        <article className="evidence-card" key={c.id}>
          <h3>
            {c.sku} · {c.field.replaceAll("_", " ")}
          </h3>
          <p>
            {c.location} · {c.quality} · Decision: {c.decision}
          </p>
          <AICandidateProvenance org={org} candidate={c} />
          <dl>
            <dt>Original source value</dt>
            <dd>
              {c.raw_value} {c.extraction?.method ? "" : c.proposed.unit}
            </dd>
            <dt>Normalized candidate</dt>
            <dd>
              {c.normalized.value === undefined ? (
                "Unknown / invalid"
              ) : (
                <>
                  {c.normalized.value} {c.normalized.unit ?? ""}
                  {c.normalized.canonical_value !== undefined && (
                    <>
                      {" "}
                      → {c.normalized.canonical_value}{" "}
                      {c.normalized.canonical_unit}
                    </>
                  )}
                </>
              )}
            </dd>
            <dt>Existing values and basis</dt>
            <dd>
              {c.existing.length
                ? JSON.stringify(c.existing)
                : "Unknown / no current value"}
            </dd>
            {!!c.proposed.competing?.length && (
              <>
                <dt>Competing candidates</dt>
                <dd>{JSON.stringify(c.proposed.competing)}</dd>
              </>
            )}
          </dl>
          {c.errors.map((e, i) => (
            <p key={i} role="alert">
              {e}
            </p>
          ))}
          {c.reviewed_at && (
            <p>
              Reviewed by actor {c.reviewed_by_id} at {c.reviewed_at}:{" "}
              {c.reason}
            </p>
          )}
          {reviewer && (
            <MutationForm
              label="Save candidate decision"
              action={async (data) => {
                await ingestion.review(org, id, c.id, {
                  expected_version: c.version,
                  decision: text(data, "decision"),
                  reason: text(data, "reason"),
                  value: text(data, "value"),
                  ...(["mass", "length", "width", "height"].includes(c.field)
                    ? { unit: text(data, "unit") }
                    : {}),
                  select_value: data.get("select_value") === "on",
                });
                reload();
              }}
            >
              <Field
                label="Reviewed value (correct if necessary)"
                name="value"
                defaultValue={String(c.normalized.value ?? c.raw_value)}
                maxLength={2000}
                required
              />
              {["mass", "length", "width", "height"].includes(c.field) && (
                <>
                  <label className="field">
                    Declared unit
                    <select
                      name="unit"
                      defaultValue={c.normalized.unit ?? c.proposed.unit}
                    >
                      <option value="">Unknown unit</option>
                      {["mm", "cm", "m", "g", "kg"].map((u) => (
                        <option key={u}>{u}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      name="select_value"
                      defaultChecked={c.select_value}
                    />{" "}
                    Explicitly select this reported measurement as canonical,
                    retaining competing claims
                  </label>
                </>
              )}
              <label className="field">
                Decision
                <select
                  name="decision"
                  defaultValue={
                    c.decision === "pending"
                      ? c.extraction?.grounded === false
                        ? "reject"
                        : "approve"
                      : c.decision
                  }
                >
                  <option
                    value="approve"
                    disabled={c.extraction?.grounded === false}
                  >
                    Approve
                  </option>
                  <option value="reject">Reject</option>
                </select>
              </label>
              <Field
                label="Review / conflict resolution reason"
                name="reason"
                defaultValue={c.reason}
                minLength={5}
                maxLength={1000}
                required
              />
            </MutationForm>
          )}
        </article>
      ))}
      {result && (
        <Pagination
          page={page}
          count={result.count}
          hasNext={!!result.next}
          change={setPage}
        />
      )}
    </section>
  );
}
function History({ org, id }: { org: string; id: string }) {
  const [result, setResult] = useState<Page<ReviewRecord> | null>(null),
    [page, setPage] = useState(1),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    void ingestion
      .history(org, id, page)
      .then((r) => {
        if (live) setResult(r);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, id, page]);
  return (
    <section className="catalog-panel">
      <h2>Import review history</h2>
      {error && <p role="alert">{error}</p>}
      <ul>
        {result?.results.map((r) => (
          <li key={r.id}>
            {r.action} · actor {r.actor_id} · {r.at} · {r.reason}
          </li>
        ))}
      </ul>
      {result && (
        <Pagination
          page={page}
          count={result.count}
          hasNext={!!result.next}
          change={setPage}
        />
      )}
    </section>
  );
}
