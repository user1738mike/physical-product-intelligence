"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { AuditEvent, Page } from "../../lib/api";
import {
  catalogPath,
  products,
  type AttributeState,
  type Claim,
  type Packaging,
  type PackagingFields,
  type PackagingRevision,
  type Product,
} from "../../lib/products";
import { AttributeSummary, ClaimCard, ClaimForm } from "./evidence";
import {
  Field,
  messageFor,
  MutationForm,
  Pagination,
  TenantFrame,
  text,
  TextField,
  useTenant,
} from "./ui";

function PackagingForm({
  org,
  product,
  initial,
  saved,
}: {
  org: string;
  product: string;
  initial?: Packaging;
  saved: (pack: Packaging) => void;
}) {
  return (
    <MutationForm
      key={initial ? `${initial.id}/${initial.version}` : "create"}
      label={initial ? "Save packaging changes" : "Create packaging profile"}
      action={async (data) => {
        const fields: PackagingFields = {
          name: text(data, "name"),
          level: text(data, "level") as Packaging["level"],
          quantity: text(data, "quantity")
            ? Number(text(data, "quantity"))
            : null,
          material: text(data, "material"),
          description: text(data, "description"),
        };
        const result = initial
          ? await products.packagingEdit(
              org,
              product,
              initial,
              fields,
              text(data, "change_reason"),
            )
          : await products.packagingCreate(org, product, fields);
        saved(result);
      }}
    >
      <div className="form-grid">
        <Field
          label="Packaging profile name"
          name="name"
          required
          maxLength={160}
          defaultValue={initial?.name}
        />
        <label className="field">
          <span>Packaging level</span>
          <select name="level" defaultValue={initial?.level ?? "unit"}>
            <option value="unit">Consumer unit</option>
            <option value="inner">Inner pack</option>
            <option value="case">Case / carton</option>
            <option value="pallet">Palletized configuration</option>
          </select>
        </label>
        <Field
          label="Units per package (optional)"
          name="quantity"
          type="number"
          min={1}
          max={1000000}
          step={1}
          defaultValue={initial?.quantity ?? ""}
        />
        <Field
          label="Packaging material (optional, reported)"
          name="material"
          maxLength={200}
          defaultValue={initial?.material}
        />
      </div>
      <TextField
        label="Packaging description (optional)"
        name="description"
        defaultValue={initial?.description}
      />
      {initial && (
        <TextField
          label="Reason for packaging changes"
          name="change_reason"
          required
          maxLength={1000}
        />
      )}
      <p className="quiet">
        Dimensions and mass start as unknown. Record evidence-backed attribute
        claims after creating the profile; no units or measurements are inferred
        from its level.
      </p>
    </MutationForm>
  );
}

function ClaimsWorkspace({
  org,
  product,
  packaging,
  privileged,
  changed,
}: {
  org: string;
  product: Product;
  packaging: Packaging | null;
  privileged: boolean;
  changed: (message: string) => void;
}) {
  const [page, setPage] = useState(1);
  const [nonce, setNonce] = useState(0);
  const [data, setData] = useState<{
    claims: Page<Claim>;
    states: AttributeState[];
  } | null>(null);
  const [error, setError] = useState("");
  const packagingId = packaging?.id;
  useEffect(() => {
    let live = true;
    setError("");
    void Promise.all([
      products.claims(org, product.id, packagingId, page),
      products.attributes(org, product.id, packagingId),
    ])
      .then(([claims, states]) => {
        if (live) setData({ claims, states: states.results });
      })
      .catch((failure) => {
        if (live) {
          setData(null);
          setError(messageFor(failure));
        }
      });
    return () => {
      live = false;
    };
  }, [org, product.id, packagingId, page, nonce]);
  const writable = product.is_active && (!packaging || packaging.is_active);
  function saved() {
    setNonce(nonce + 1);
    changed(
      "Evidence review updated. Prior claims and history have been preserved.",
    );
  }
  return (
    <section id="evidence" aria-labelledby="evidence-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">EVIDENCE & DATA QUALITY</p>
          <h2 id="evidence-title">
            {packaging
              ? `Claims for ${packaging.name}`
              : "Claims for the product"}
          </h2>
        </div>
        <span className="badge unknown">
          {packaging ? "Packaging scope" : "Product scope"}
        </span>
      </div>
      <p>
        Reported specifications, estimates and physical measurements are
        separate claims. A conflicting source never overwrites an earlier
        observation.
      </p>
      {error ? (
        <div className="notice error" role="alert">
          <p>{error}</p>
          <button onClick={() => setNonce(nonce + 1)}>Retry evidence</button>
        </div>
      ) : !data ? (
        <p role="status">Loading attribute provenance…</p>
      ) : (
        <>
          <AttributeSummary states={data.states} />
          <div className="evidence-layout">
            <div>
              <h3>Source claims</h3>
              {data.claims.results.length === 0 ? (
                <div className="panel empty">
                  <h3>No attribute claims yet</h3>
                  <p>
                    Physical values remain unknown. Add a reported specification
                    or estimate with its source; physical verification requires
                    an authorized measurement record.
                  </p>
                </div>
              ) : (
                data.claims.results.map((claim) => (
                  <ClaimCard
                    key={`${claim.id}/${nonce}`}
                    claim={claim}
                    org={org}
                    product={product.id}
                    packaging={packagingId}
                    privileged={privileged}
                    writable={writable}
                    saved={saved}
                  />
                ))
              )}
              <Pagination
                page={page}
                count={data.claims.count}
                hasNext={data.claims.next !== null}
                change={setPage}
              />
            </div>
            <aside className="panel evidence-editor">
              <h3>Add an attribute claim</h3>
              {writable ? (
                <ClaimForm
                  org={org}
                  product={product.id}
                  packaging={packagingId}
                  saved={saved}
                />
              ) : (
                <p className="notice">
                  This {product.is_active ? "packaging profile" : "product"} is
                  archived. Its evidence remains readable; reactivate it before
                  adding claims or verification.
                </p>
              )}
            </aside>
          </div>
        </>
      )}
    </section>
  );
}

function History({
  org,
  product,
  packaging,
  nonce,
}: {
  org: string;
  product: string;
  packaging?: string;
  nonce: number;
}) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AuditEvent> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setData(null);
    setError("");
    void products
      .history(org, product, packaging, page)
      .then((value) => {
        if (live) setData(value);
      })
      .catch((failure) => {
        if (live) setError(messageFor(failure));
      });
    return () => {
      live = false;
    };
  }, [org, product, packaging, page, nonce]);
  return (
    <section id="history" aria-labelledby="history-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">CHANGE HISTORY</p>
          <h2 id="history-title">A reviewable record of changes.</h2>
        </div>
      </div>
      {error ? (
        <p role="alert" className="notice error">
          {error}
        </p>
      ) : !data ? (
        <p role="status">Loading history…</p>
      ) : (
        <>
          <div className="panel table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Change</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Time</th>
                  <th scope="col">Resource</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((event) => (
                  <tr key={event.id}>
                    <th scope="row">
                      {event.action.replaceAll(".", " · ").replaceAll("_", " ")}
                    </th>
                    <td>{event.actor_id ?? "Removed actor"}</td>
                    <td>{new Date(event.timestamp).toLocaleString()}</td>
                    <td className="mono">
                      {event.target_type}
                      <small>{event.target_id}</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            count={data.count}
            hasNext={data.next !== null}
            change={setPage}
          />
        </>
      )}
    </section>
  );
}

function PackagingHistory({
  org,
  product,
  packaging,
}: {
  org: string;
  product: string;
  packaging: Packaging;
}) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<PackagingRevision> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    void products
      .packagingRevisions(org, product, packaging.id, page)
      .then((value) => {
        if (live) setData(value);
      })
      .catch((failure) => {
        if (live) setError(messageFor(failure));
      });
    return () => {
      live = false;
    };
  }, [org, product, packaging.id, packaging.version, page]);
  return (
    <details className="panel">
      <summary>Packaging descriptor revision history</summary>
      {error ? (
        <p role="alert">{error}</p>
      ) : !data ? (
        <p role="status">Loading packaging revisions…</p>
      ) : (
        <>
          <ol className="revision-list">
            {data.results.map((row) => (
              <li key={row.id}>
                <strong>
                  Version {row.version}: {row.name}
                </strong>
                <p>
                  {row.level} · quantity {row.quantity ?? "unknown"} · material{" "}
                  {row.material || "unknown"} ·{" "}
                  {row.is_active ? "active" : "archived"}
                </p>
                <p>{row.description || "No description supplied"}</p>
                <p>Reason: {row.change_reason}</p>
                <small>
                  Actor {row.changed_by_id ?? "removed"} ·{" "}
                  {new Date(row.recorded_at).toLocaleString()}
                </small>
              </li>
            ))}
          </ol>
          <Pagination
            page={page}
            count={data.count}
            hasNext={data.next !== null}
            change={setPage}
          />
        </>
      )}
    </details>
  );
}

function Detail({ org, id }: { org: string; id: string }) {
  const membership = useTenant();
  const privileged = membership.role === "owner" || membership.role === "admin";
  const [product, setProduct] = useState<Product | null>(null);
  const [packaging, setPackaging] = useState<Page<Packaging> | null>(null);
  const [packPage, setPackPage] = useState(1);
  const [selected, setSelected] = useState<Packaging | null>(null);
  const [nonce, setNonce] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setError("");
    void Promise.all([
      products.get(org, id),
      products.packaging(org, id, packPage),
    ])
      .then(([record, profiles]) => {
        if (live) {
          setProduct(record);
          setPackaging(profiles);
        }
      })
      .catch((failure) => {
        if (live) {
          setProduct(null);
          setPackaging(null);
          setError(messageFor(failure));
        }
      });
    return () => {
      live = false;
    };
  }, [org, id, packPage, nonce]);
  function changed(value: string) {
    setMessage(value);
    setNonce(nonce + 1);
  }
  function packagingSaved(pack: Packaging) {
    setSelected(pack);
    changed("Packaging saved. Previous versions remain in history.");
  }
  if (error)
    return (
      <div className="notice error" role="alert">
        <p>{error}</p>
        <button onClick={() => setNonce(nonce + 1)}>Retry product</button>
      </div>
    );
  if (!product || !packaging)
    return (
      <p role="status" className="loading">
        Loading product record…
      </p>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PRODUCT RECORD · {product.sku}</p>
          <h1>{product.name}</h1>
          <p>
            {product.brand ||
              product.manufacturer ||
              "Brand / manufacturer not supplied"}{" "}
            · Revision {product.latest_revision_number}
          </p>
        </div>
        <div className="actions">
          <span className={`badge ${product.is_active ? "active" : "unknown"}`}>
            {product.is_active ? "Active" : "Archived"}
          </span>
          {product.is_active && (
            <Link
              className="button-link"
              href={`${catalogPath(org)}/${id}/edit`}
            >
              Edit product
            </Link>
          )}
          <Link href={catalogPath(org)}>Back to catalog</Link>
        </div>
      </div>
      <nav className="section-nav" aria-label="Product sections">
        <a href="#overview">Overview</a>
        <a href="#packaging">Packaging</a>
        <a href="#evidence">Attribute evidence</a>
        <a href="#history">History</a>
      </nav>
      {message && (
        <p className="notice success" role="status">
          {message}
        </p>
      )}
      <section id="overview" className="panel" aria-labelledby="overview-title">
        <div className="section-heading">
          <h2 id="overview-title">
            Catalog details{" "}
            <span className="badge reported">Reported metadata</span>
          </h2>
        </div>
        <p>{product.description || "No product description supplied."}</p>
        <dl className="detail-grid">
          <div>
            <dt>SKU</dt>
            <dd className="mono">{product.sku}</dd>
          </div>
          <div>
            <dt>Brand</dt>
            <dd>{product.brand || "Unknown"}</dd>
          </div>
          <div>
            <dt>Manufacturer</dt>
            <dd>{product.manufacturer || "Unknown"}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{product.model_number || "Unknown"}</dd>
          </div>
          <div>
            <dt>Category</dt>
            <dd>{product.category || "Unknown"}</dd>
          </div>
          <div>
            <dt>Last catalog edit</dt>
            <dd>{new Date(product.updated_at).toLocaleString()}</dd>
          </div>
        </dl>
        {privileged && (
          <MutationForm
            label={product.is_active ? "Archive product" : "Reactivate product"}
            action={async () => {
              const saved = await products.state(org, id, !product.is_active);
              setProduct(saved);
              changed(
                saved.is_active
                  ? "Product reactivated."
                  : "Product archived. History and evidence are retained.",
              );
            }}
          >
            <p className="quiet">
              Archival retains all records and stops new edits, claims and
              verification. Only owners and admins can change lifecycle status.
            </p>
          </MutationForm>
        )}
      </section>
      <section id="packaging" aria-labelledby="packaging-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PACKAGING CONFIGURATIONS</p>
            <h2 id="packaging-title">From a consumer unit to a pallet.</h2>
          </div>
        </div>
        {packaging.results.length === 0 ? (
          <div className="panel empty">
            <h3>No packaging profiles yet</h3>
            <p>
              Add a named configuration. Missing physical measurements remain
              unknown.
            </p>
          </div>
        ) : (
          <div className="packaging-grid">
            {packaging.results.map((pack) => (
              <article
                className={`panel packaging-card ${selected?.id === pack.id ? "selected" : ""}`}
                key={pack.id}
              >
                <div className="claim-heading">
                  <h3>{pack.name}</h3>
                  <span
                    className={`badge ${pack.is_active ? "active" : "unknown"}`}
                  >
                    {pack.is_active ? "Active" : "Archived"}
                  </span>
                </div>
                <p>
                  {pack.level} · version {pack.version}
                </p>
                <p>Units per package: {pack.quantity ?? "Unknown"}</p>
                <p>
                  Material: {pack.material || "Unknown"}{" "}
                  <small>Contributor-reported</small>
                </p>
                <p>{pack.description}</p>
                <button
                  type="button"
                  aria-pressed={selected?.id === pack.id}
                  onClick={() => {
                    setSelected(pack);
                    setMessage(
                      `Reviewing attribute evidence for ${pack.name}.`,
                    );
                  }}
                >
                  Review packaging & evidence
                </button>
              </article>
            ))}
          </div>
        )}
        <Pagination
          page={packPage}
          count={packaging.count}
          hasNext={packaging.next !== null}
          change={setPackPage}
        />
        {product.is_active && (
          <details className="panel">
            <summary>Add packaging configuration</summary>
            <PackagingForm org={org} product={id} saved={packagingSaved} />
          </details>
        )}
        {selected && (
          <section className="selected-profile panel">
            <div className="section-heading">
              <h3>Selected packaging: {selected.name}</h3>
              <button
                type="button"
                className="secondary"
                onClick={() => setSelected(null)}
              >
                Return to product attributes
              </button>
            </div>
            {product.is_active && selected.is_active && (
              <details>
                <summary>Edit packaging profile</summary>
                <PackagingForm
                  org={org}
                  product={id}
                  initial={selected}
                  saved={packagingSaved}
                />
              </details>
            )}
            {privileged && product.is_active && (
              <MutationForm
                label={
                  selected.is_active
                    ? "Archive packaging profile"
                    : "Reactivate packaging profile"
                }
                action={async () =>
                  packagingSaved(
                    await products.packagingState(
                      org,
                      id,
                      selected,
                      !selected.is_active,
                    ),
                  )
                }
              >
                <p className="quiet">
                  Archived packaging retains its claims and change history.
                </p>
              </MutationForm>
            )}
            <PackagingHistory
              key={`${selected.id}/${selected.version}`}
              org={org}
              product={id}
              packaging={selected}
            />
          </section>
        )}
      </section>
      <ClaimsWorkspace
        key={`claims/${selected?.id ?? "product"}`}
        org={org}
        product={product}
        packaging={selected}
        privileged={privileged}
        changed={changed}
      />
      <History
        key={`history/${selected?.id ?? "product"}`}
        org={org}
        product={id}
        packaging={selected?.id}
        nonce={nonce}
      />
      <p className="notice">
        This record supports evidence review. It makes no robot-compatibility,
        certification or handling-safety determination.
      </p>
    </>
  );
}
export function ProductDetailPage({ org, id }: { org: string; id: string }) {
  return (
    <TenantFrame key={`${org}/${id}`} org={org}>
      <Detail org={org} id={id} />
    </TenantFrame>
  );
}
