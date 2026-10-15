"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  compatibility,
  equipmentPath,
  assessmentPath,
  type Assessment,
  type AssessmentSummary,
  type Equipment,
  type RuleSet,
  type RuleResult,
} from "../../lib/compatibility";
import { products, type Product, type Packaging } from "../../lib/products";
import type { Page } from "../../lib/api";
import {
  Field,
  MutationForm,
  Pagination,
  TenantFrame,
  messageFor,
  text,
} from "../products/ui";

export const assessmentDisclaimer =
  "Recorded-input compatibility only. This is not physical validation, robot safety certification, or a guarantee of successful handling.";
export function AssessmentWorkspace({
  org,
  parent,
}: {
  org: string;
  parent?: string;
}) {
  return (
    <TenantFrame org={org}>
      <Workspace org={org} parent={parent} />
    </TenantFrame>
  );
}

function Workspace({ org, parent }: { org: string; parent?: string }) {
  const [product, setProduct] = useState<Product | null>(null),
    [equipment, setEquipment] = useState<Equipment | null>(null),
    [packages, setPackages] = useState<Packaging[]>([]),
    [ruleSets, setRuleSets] = useState<RuleSet[]>([]),
    [previous, setPrevious] = useState<Assessment | null>(null),
    [packagingId, setPackagingId] = useState(""),
    [error, setError] = useState("");
  const [requestId] = useState(() => crypto.randomUUID());
  useEffect(() => {
    let live = true;
    if (parent)
      void compatibility
        .assessment(org, parent)
        .then(async (a) => {
          const [p, e] = await Promise.all([
            products.get(org, a.product_id),
            compatibility.profile(org, a.equipment_id),
          ]);
          if (live) {
            setPrevious(a);
            setPackagingId(a.packaging_id ?? "");
            setProduct(p);
            setEquipment(e);
          }
        })
        .catch((e) => {
          if (live) setError(messageFor(e));
        });
    return () => {
      live = false;
    };
  }, [org, parent]);
  useEffect(() => {
    let live = true;
    async function load() {
      const rows: Packaging[] = [];
      if (product) {
        let page = 1;
        while (true) {
          const r = await products.packaging(org, product.id, page);
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
  }, [org, product]);
  useEffect(() => {
    let live = true;
    async function load() {
      const rows: RuleSet[] = [];
      if (equipment) {
        let page = 1;
        while (true) {
          const r = await compatibility.rules(org, equipment.id, page);
          rows.push(...r.results);
          if (!r.next) break;
          page++;
        }
      }
      if (live)
        setRuleSets(
          rows.filter(
            (r) =>
              r.activation &&
              r.equipment_revision_id === equipment?.revision_id,
          ),
        );
    }
    void load().catch((e) => {
      if (live) setError(messageFor(e));
    });
    return () => {
      live = false;
    };
  }, [org, equipment]);
  return (
    <>
      <h1>Compatibility assessments</h1>
      <p>{assessmentDisclaimer}</p>
      {error && <p role="alert">{error}</p>}
      <section className="catalog-panel">
        <h2>Choose current inputs</h2>
        {previous && (
          <p>
            New assessment linked to{" "}
            <Link href={`${assessmentPath(org)}/${previous.id}`}>
              previous snapshot
            </Link>
            . Current catalog data and explicitly selected rules will be
            evaluated.
          </p>
        )}
        <ProductPicker
          org={org}
          selected={product?.id}
          choose={(p) => {
            setProduct(p);
            setPackagingId("");
          }}
        />
        <EquipmentPicker
          org={org}
          selected={equipment?.id}
          choose={setEquipment}
        />
        {product && equipment && (
          <MutationForm
            key={`${product.id}-${equipment.id}-${previous?.id ?? "new"}`}
            label="Run compatibility assessment"
            action={async (data) => {
              const result = await compatibility.assess(org, {
                request_id: requestId,
                product_id: product.id,
                equipment_id: equipment.id,
                packaging_id: text(data, "packaging_id") || null,
                rule_set_id: text(data, "rule_set_id"),
                orientation: text(data, "orientation") || null,
                product_level: text(data, "packaging_id")
                  ? null
                  : text(data, "product_level") || null,
                parent_id: previous?.id ?? null,
              });
              window.location.assign(`${assessmentPath(org)}/${result.id}`);
            }}
          >
            <p>
              Product: {product.name} · Equipment: {equipment.definition.name}
            </p>
            <label className="field">
              Product / packaging scope
              <select
                name="packaging_id"
                value={packagingId}
                onChange={(event) => setPackagingId(event.target.value)}
              >
                <option value="">Product-level claims</option>
                {packages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.level} · version {p.version}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Product-level handling context (used only without a package)
              <select
                name="product_level"
                defaultValue={
                  previous?.packaging_id
                    ? ""
                    : (previous?.inputs.handling_level ?? "")
                }
              >
                <option value="">Unknown handling level</option>
                {["unit", "inner", "case", "pallet"].map((l) => (
                  <option key={l}>{l}</option>
                ))}
              </select>
            </label>
            <label className="field">
              Explicit orientation
              <select
                name="orientation"
                defaultValue={previous?.inputs.orientation ?? ""}
              >
                <option value="">
                  Unknown orientation → dimensions indeterminate
                </option>
                <option value="as_recorded">
                  As recorded: length / width / height unchanged
                </option>
                <option value="swap_length_width">
                  Swap length and width; height unchanged
                </option>
              </select>
            </label>
            <label className="field">
              Eligible activated rule-set version
              <select name="rule_set_id" required defaultValue="">
                <option value="">Choose an activated version</option>
                {ruleSets.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} · version {r.number} · {r.evidence_policy}
                  </option>
                ))}
              </select>
            </label>
            {!ruleSets.length && (
              <p className="notice">
                No eligible activated rule set for this specification. An
                owner/admin must review and activate one.
              </p>
            )}
            <p>
              Unknown required measurements/specifications and conflicting
              claims prevent a compatible result. Estimated inputs never become
              measured facts.
            </p>
          </MutationForm>
        )}
      </section>
      <History org={org} />
    </>
  );
}

function ProductPicker({
  org,
  selected,
  choose,
}: {
  org: string;
  selected?: string;
  choose: (p: Product) => void;
}) {
  const [result, setResult] = useState<Page<Product> | null>(null),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(1),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
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
  }, [org, search, page]);
  return (
    <fieldset>
      <legend>Product selection</legend>
      <MutationForm
        label="Search products for assessment"
        action={async (data) => {
          setSearch(text(data, "search"));
          setPage(1);
        }}
      >
        <Field label="Product SKU or name" name="search" maxLength={100} />
      </MutationForm>
      {error && <p role="alert">{error}</p>}
      <ul className="record-list">
        {result?.results.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              aria-pressed={selected === p.id}
              onClick={() => choose(p)}
            >
              {p.sku} · {p.name}
              {selected === p.id ? " · selected" : ""}
            </button>
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
    </fieldset>
  );
}
function EquipmentPicker({
  org,
  selected,
  choose,
}: {
  org: string;
  selected?: string;
  choose: (p: Equipment) => void;
}) {
  const [result, setResult] = useState<Page<Equipment> | null>(null),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(1),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    void compatibility
      .equipment(org, { search, page, status: "active" })
      .then((r) => {
        if (live) setResult(r);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, search, page]);
  return (
    <fieldset>
      <legend>Active equipment selection</legend>
      <MutationForm
        label="Search equipment for assessment"
        action={async (data) => {
          setSearch(text(data, "search"));
          setPage(1);
        }}
      >
        <Field label="Equipment code or name" name="search" maxLength={100} />
      </MutationForm>
      {error && <p role="alert">{error}</p>}
      <ul className="record-list">
        {result?.results.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              aria-pressed={selected === p.id}
              onClick={() => choose(p)}
            >
              {p.code} · {p.definition.name}
              {selected === p.id ? " · selected" : ""}
            </button>
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
    </fieldset>
  );
}

function History({ org }: { org: string }) {
  const [result, setResult] = useState<Page<AssessmentSummary> | null>(null),
    [page, setPage] = useState(1),
    [filters, setFilters] = useState<Record<string, string>>({}),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    void compatibility
      .assessments(org, { ...filters, page })
      .then((r) => {
        if (live) setResult(r);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, page, filters]);
  return (
    <section className="catalog-panel">
      <h2>Assessment history</h2>
      <MutationForm
        label="Filter assessment history"
        action={async (data) => {
          const f = Object.fromEntries(
            ["product_id", "equipment_id", "overall"].map((k) => [
              k,
              text(data, k),
            ]),
          );
          for (const k of ["date_from", "date_to"])
            if (text(data, k)) f[k] = new Date(text(data, k)).toISOString();
          setFilters(f);
          setPage(1);
        }}
      >
        <div className="form-grid">
          <Field label="Product UUID filter (optional)" name="product_id" />
          <Field label="Equipment UUID filter (optional)" name="equipment_id" />
          <label className="field">
            Overall result filter
            <select name="overall">
              <option value="">All results</option>
              {["compatible", "incompatible", "indeterminate"].map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
          <Field
            label="From (local time)"
            name="date_from"
            type="datetime-local"
          />
          <Field
            label="Through (local time)"
            name="date_to"
            type="datetime-local"
          />
        </div>
      </MutationForm>
      {error && <p role="alert">{error}</p>}
      {!result ? (
        <p role="status">Loading immutable history…</p>
      ) : (
        <>
          <ul className="record-list">
            {result.results.map((a) => (
              <li key={a.id}>
                <Link href={`${assessmentPath(org)}/${a.id}`}>
                  {a.overall} · {a.created_at}
                </Link>
                <p>
                  Product {a.product_id} · Equipment {a.equipment_id} · Actor{" "}
                  {a.created_by_id}
                </p>
              </li>
            ))}
          </ul>
          {!result.count && <p>No assessments match.</p>}
          <Pagination
            page={page}
            count={result.count}
            hasNext={!!result.next}
            change={setPage}
          />
        </>
      )}
    </section>
  );
}

export function AssessmentDetail({ org, id }: { org: string; id: string }) {
  return (
    <TenantFrame org={org}>
      <Detail org={org} id={id} />
    </TenantFrame>
  );
}
function Detail({ org, id }: { org: string; id: string }) {
  const [assessment, setAssessment] = useState<Assessment | null>(null),
    [error, setError] = useState(""),
    [comparison, setComparison] = useState<Awaited<
      ReturnType<typeof compatibility.compare>
    > | null>(null);
  useEffect(() => {
    let live = true;
    void compatibility
      .assessment(org, id)
      .then((a) => {
        if (live) setAssessment(a);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, id]);
  if (error) return <p role="alert">{error}</p>;
  if (!assessment) return <p role="status">Loading immutable assessment…</p>;
  return (
    <>
      <Link href={assessmentPath(org)}>Assessments and history</Link>
      <AssessmentResult org={org} assessment={assessment} />
      <Link
        href={`${assessmentPath(org)}?parent=${encodeURIComponent(assessment.id)}`}
      >
        Reassess these targets using current data
      </Link>
      <section className="catalog-panel">
        <h2>Compare historical assessments</h2>
        <MutationForm
          label="Compare assessment snapshots"
          action={async (data) =>
            setComparison(
              await compatibility.compare(org, id, text(data, "other_id")),
            )
          }
        >
          <Field
            label="Other assessment UUID (same product, scope and equipment)"
            name="other_id"
            defaultValue={assessment.parent_id ?? ""}
            required
          />
        </MutationForm>
        {comparison && (
          <>
            <p>
              {comparison.first_result} → {comparison.second_result} ·{" "}
              {comparison.changes.length} changed rule results
            </p>
            {comparison.changes.map((c) => (
              <details key={c.rule_id}>
                <summary>
                  {c.after?.name ?? c.before?.name ?? c.rule_id}:{" "}
                  {c.before?.status ?? "absent"} → {c.after?.status ?? "absent"}
                </summary>
                <pre className="snapshot-json">
                  {JSON.stringify(
                    { before: c.before, after: c.after },
                    null,
                    2,
                  )}
                </pre>
              </details>
            ))}
          </>
        )}
      </section>
    </>
  );
}

export function constraintDescription(r: RuleResult): string {
  const expected = r.expected;
  if (!expected) return "Specification unknown.";
  if (Array.isArray(expected))
    return `Allowed configurations: ${expected.join(", ")}.`;
  if (Array.isArray(expected.allowed))
    return `Allowed configurations: ${expected.allowed.join(", ")}.`;
  if (expected.limit !== undefined)
    return `${r.type === "minimum" ? "Minimum" : "Maximum"} ${expected.limit} ${expected.unit}; clearance ${expected.margin ?? "0"} ${expected.unit}; inclusive effective limit ${expected.effective_limit ?? "unknown"} ${expected.canonical_unit ?? expected.unit}.`;
  return "Required qualifying attribute evidence.";
}

export function AssessmentResult({
  org,
  assessment: a,
}: {
  org: string;
  assessment: Assessment;
}) {
  return (
    <>
      <h1>Assessment: {a.overall}</h1>
      <p className="notice">{assessmentDisclaimer}</p>
      <section className="catalog-panel">
        <h2>Historical snapshot</h2>
        <p>{a.summary}</p>
        <p>
          {a.created_at} · actor {a.created_by_id} · engine {a.engine_version} ·
          schema {a.rule_snapshot.schema_version}
        </p>
        <p>
          <Link href={`/organizations/${org}/products/${a.product_id}`}>
            {a.inputs.product.sku} · {a.inputs.product.name}
          </Link>{" "}
          · product revision {a.inputs.product.latest_revision_number}
        </p>
        <p>
          Packaging:{" "}
          {a.inputs.packaging
            ? `${a.inputs.packaging.name} · version ${a.inputs.packaging.version}`
            : "Product scope"}{" "}
          · level {a.inputs.handling_level ?? "unknown"} ({a.inputs.level_basis}
          )
        </p>
        <p>
          <Link href={`${equipmentPath(org)}/${a.equipment_id}`}>
            {a.equipment_snapshot.definition.name}
          </Link>{" "}
          · equipment specification {a.equipment_snapshot.number} · rule-set{" "}
          {a.rule_snapshot.number} · {a.rule_snapshot.evidence_policy}
        </p>
        <p>
          Orientation: {a.inputs.orientation ?? "unknown"}. Current linked
          records may have changed; the values below are the retained evaluation
          inputs.
        </p>
      </section>
      <section className="catalog-panel">
        <h2>Evidence quality and missing inputs</h2>
        <ul>
          {Object.entries(a.inputs.attributes).map(([attribute, state]) => (
            <li key={attribute}>
              <strong>{attribute}</strong>:{" "}
              {state.conflicting
                ? "Conflicting claims — canonical editorial selection does not remove disagreement"
                : state.claims.length
                  ? state.quality_status
                  : "Missing / unknown"}{" "}
              · {state.claims.length} retained claims
              {state.claims.some((c) => c.basis === "estimated") && (
                <span> · Estimates present; insufficient for a pass</span>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section className="catalog-panel">
        <h2>Per-rule explanations</h2>
        {a.results.map((r, i) => (
          <article className="evidence-card" key={`${r.rule_id}-${i}`}>
            <h3>
              {r.name} · {r.status.replaceAll("_", " ")}
            </h3>
            <p>
              {r.severity} · rule {r.rule_id} version {r.rule_version} ·
              rule-set {r.rule_set_version}
            </p>
            <p>{r.reason}</p>
            {r.explanation && <p>{r.explanation}</p>}
            <p>
              Attribute: {r.attribute}
              {r.recorded_attribute && r.recorded_attribute !== r.attribute
                ? ` · recorded axis ${r.recorded_attribute}`
                : ""}
            </p>
            {r.expected && <p>{constraintDescription(r)}</p>}
            {r.recorded_value !== undefined && (
              <p>Recorded configuration: {r.recorded_value ?? "Unknown"}</p>
            )}
            {!!r.recorded_values?.length && (
              <details>
                <summary>
                  Recorded values, original units and provenance (
                  {r.recorded_values.length})
                </summary>
                {r.recorded_values.map((c) => (
                  <div key={c.id}>
                    <p>
                      {c.value} {c.unit} → {c.canonical_value}{" "}
                      {c.canonical_unit} ·{" "}
                      {c.basis === "measured"
                        ? "Physically measured (attested)"
                        : c.basis === "estimated"
                          ? "Estimated — not verified"
                          : "Reported — not verified"}{" "}
                      ·{" "}
                      {r.used_claim_ids.includes(c.id)
                        ? "Qualifying input"
                        : "Not qualifying under evidence policy"}
                    </p>
                    <p>
                      Bounds: {c.lower ?? "point value"} /{" "}
                      {c.upper ?? "point value"} · {c.evidence.title} ·{" "}
                      {c.evidence.source_reference}
                    </p>
                    <p>
                      {c.method} · {c.limitations} · actor {c.recorded_by_id} ·{" "}
                      {c.recorded_at}
                    </p>
                    {c.evidence.source_artifact && (
                      <a href={c.evidence.source_artifact.download_path}>
                        Authorized private source ·{" "}
                        {c.evidence.source_artifact.location}
                      </a>
                    )}
                  </div>
                ))}
              </details>
            )}
            {r.source_reference && (
              <p>Specification reference: {r.source_reference}</p>
            )}
            {r.source?.kind === "import" && (
              <a
                href={`/api/v1/organizations/${org}/imports/${r.source.id}/file/`}
              >
                Authorized private specification
              </a>
            )}
          </article>
        ))}
      </section>
    </>
  );
}
