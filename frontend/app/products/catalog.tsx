"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Membership, type Page } from "../../lib/api";
import { organizationPath } from "../../lib/workspace";
import {
  catalogPath,
  products,
  type Product,
  type ProductFields,
} from "../../lib/products";
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

export function OrganizationPicker() {
  const [items, setItems] = useState<Page<Membership> | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setItems(null);
    setError("");
    void api
      .memberships(page)
      .then((result) => {
        if (live) setItems(result);
      })
      .catch((failure) => {
        if (live) setError(messageFor(failure));
      });
    return () => {
      live = false;
    };
  }, [page]);
  return (
    <main className="catalog-shell">
      <header className="masthead">
        <Link href="/" className="brand">
          Physical Product Intelligence Cloud
        </Link>
        <Link href="/account">Account / Sign in</Link>
      </header>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR WORKSPACE</p>
          <h1>Your organizations</h1>
          <p>
            Choose an organization to open its overview, products and evidence.
          </p>
        </div>
      </div>
      {error ? (
        <div role="alert" className="notice error">
          <p>{error}</p>
          <Link href="/account">Sign in or manage your organizations</Link>
        </div>
      ) : !items ? (
        <p role="status">Loading organizations…</p>
      ) : (
        <>
          {items.results.length === 0 ? (
            <section className="panel empty">
              <h2>No organizations yet</h2>
              <p>
                Create an organization from your account to start a product
                catalog.
              </p>
              <Link href="/account">Open account</Link>
            </section>
          ) : (
            <div className="organization-grid">
              {items.results.map((item) => (
                <section className="panel" key={item.id}>
                  <p className="eyebrow">{item.role}</p>
                  <h2>{item.organization.name}</h2>
                  {item.organization.is_active ? (
                    <Link
                      className="button-link"
                      href={organizationPath(item.organization.id)}
                    >
                      Open dashboard
                    </Link>
                  ) : (
                    <p className="notice">
                      Organization suspended.{" "}
                      <Link
                        href={organizationPath(
                          item.organization.id,
                          "settings",
                        )}
                      >
                        Open organization settings
                      </Link>{" "}
                      for permitted recovery and management.
                    </p>
                  )}
                </section>
              ))}
            </div>
          )}
          <Pagination
            page={page}
            count={items.count}
            hasNext={items.next !== null}
            change={setPage}
          />
        </>
      )}
    </main>
  );
}

function Catalog({ org }: { org: string }) {
  const [query, setQuery] = useState({
    search: "",
    status: "all",
    ordering: "sku",
    page: 1,
  });
  const [result, setResult] = useState<Page<Product> | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setResult(null);
    setError("");
    void products
      .list(org, query)
      .then((value) => {
        if (live) setResult(value);
      })
      .catch((failure) => {
        if (live) setError(messageFor(failure));
      });
    return () => {
      live = false;
    };
  }, [org, query, attempt]);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PRODUCT CATALOG</p>
          <h1>Products with a traceable history.</h1>
          <p>
            Keep catalog records, packaging configurations and source claims
            together.
          </p>
        </div>
        <Link className="button-link" href={`${catalogPath(org)}/new`}>
          Create product
        </Link>
      </div>
      <form
        className="catalog-search panel"
        aria-label="Search catalog"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          setQuery({
            search: text(data, "search"),
            status: text(data, "status"),
            ordering: text(data, "ordering"),
            page: 1,
          });
        }}
      >
        <Field
          label="Search by SKU or product name"
          name="search"
          type="search"
          maxLength={100}
          defaultValue={query.search}
        />
        <label className="field">
          <span>Lifecycle</span>
          <select name="status" defaultValue="all">
            <option value="all">All products</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <label className="field">
          <span>Sort by</span>
          <select name="ordering" defaultValue="sku">
            <option value="sku">SKU A–Z</option>
            <option value="-sku">SKU Z–A</option>
            <option value="name">Name A–Z</option>
            <option value="-updated_at">Recently updated</option>
          </select>
        </label>
        <button type="submit">Search</button>
      </form>
      {error ? (
        <div className="notice error" role="alert">
          <p>{error}</p>
          <button onClick={() => setAttempt(attempt + 1)}>Retry catalog</button>
        </div>
      ) : !result ? (
        <p className="loading" role="status">
          Loading products…
        </p>
      ) : (
        <>
          {result.results.length === 0 ? (
            <section className="panel empty">
              <h2>
                {query.search
                  ? "No matching products"
                  : "No products in this view"}
              </h2>
              <p>
                Try another search or create your first structured product
                record.
              </p>
              <Link href={`${catalogPath(org)}/new`}>Create product</Link>
            </section>
          ) : (
            <section className="panel table-wrap" aria-label="Product results">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Product</th>
                    <th scope="col">SKU</th>
                    <th scope="col">Category</th>
                    <th scope="col">Revision</th>
                    <th scope="col">Status</th>
                    <th scope="col">Open</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((product) => (
                    <tr key={product.id}>
                      <th scope="row">
                        <Link href={`${catalogPath(org)}/${product.id}`}>
                          {product.name}
                        </Link>
                        <small>
                          {product.brand ||
                            product.manufacturer ||
                            "Brand not supplied"}
                        </small>
                      </th>
                      <td className="mono">{product.sku}</td>
                      <td>{product.category || "Unknown"}</td>
                      <td>{product.latest_revision_number}</td>
                      <td>
                        <span
                          className={`badge ${product.is_active ? "active" : "unknown"}`}
                        >
                          {product.is_active ? "Active" : "Archived"}
                        </span>
                      </td>
                      <td>
                        <Link
                          href={`${catalogPath(org)}/${product.id}`}
                          aria-label={`View ${product.name}`}
                        >
                          View record →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          <Pagination
            page={query.page}
            count={result.count}
            hasNext={result.next !== null}
            change={(page) => setQuery({ ...query, page })}
          />
        </>
      )}
      <p className="quiet">
        Catalog details are contributor-reported. Physical attributes stay
        unknown until claims are recorded; verification and conflict decisions
        are shown on each record.
      </p>
    </>
  );
}

export function CatalogPage({ org }: { org: string }) {
  return (
    <TenantFrame key={org} org={org}>
      <Catalog org={org} />
    </TenantFrame>
  );
}

function ProductEditor({ org, id }: { org: string; id?: string }) {
  useTenant();
  const router = useRouter();
  const [product, setProduct] = useState<Product | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!id) return;
    let live = true;
    void products
      .get(org, id)
      .then((value) => {
        if (live) setProduct(value);
      })
      .catch((failure) => {
        if (live) setError(messageFor(failure));
      });
    return () => {
      live = false;
    };
  }, [org, id]);
  if (error)
    return (
      <p role="alert" className="notice error">
        {error}
      </p>
    );
  if (id && !product) return <p role="status">Loading product for editing…</p>;
  if (product && !product.is_active)
    return (
      <section className="notice">
        <h1>Archived product</h1>
        <p>Reactivate this product before editing it.</p>
        <Link href={`${catalogPath(org)}/${product.id}`}>
          Return to product
        </Link>
      </section>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CATALOG RECORD</p>
          <h1>{id ? "Edit product" : "Create a product"}</h1>
          <p>
            Product edits preserve the previous revision. Dimensions and
            verification are managed as evidence-backed claims.
          </p>
        </div>
        <Link href={id ? `${catalogPath(org)}/${id}` : catalogPath(org)}>
          Cancel
        </Link>
      </div>
      <section className="panel editor-panel">
        <MutationForm
          label={id ? "Save product changes" : "Create product"}
          action={async (data) => {
            const fields = Object.fromEntries(
              [
                "name",
                "description",
                "brand",
                "manufacturer",
                "model_number",
                "category",
              ].map((field) => [field, text(data, field)]),
            ) as ProductFields;
            const saved =
              id && product
                ? await products.edit(
                    org,
                    id,
                    fields,
                    product.latest_revision_number,
                    text(data, "change_reason"),
                  )
                : await products.create(
                    org,
                    text(data, "sku"),
                    fields,
                    text(data, "change_reason"),
                  );
            router.push(`${catalogPath(org)}/${saved.id}`);
            router.refresh();
          }}
        >
          <div className="form-grid">
            <Field
              label="Organization SKU"
              name="sku"
              required
              maxLength={100}
              pattern="[A-Za-z0-9][A-Za-z0-9._\-]*"
              defaultValue={product?.sku}
              readOnly={Boolean(id)}
            />
            <Field
              label="Product name"
              name="name"
              required
              maxLength={200}
              defaultValue={product?.name}
            />
            <Field
              label="Brand (optional)"
              name="brand"
              maxLength={160}
              defaultValue={product?.brand}
            />
            <Field
              label="Manufacturer (optional)"
              name="manufacturer"
              maxLength={160}
              defaultValue={product?.manufacturer}
            />
            <Field
              label="Model number (optional)"
              name="model_number"
              maxLength={160}
              defaultValue={product?.model_number}
            />
            <Field
              label="Category (optional)"
              name="category"
              maxLength={160}
              defaultValue={product?.category}
            />
          </div>
          <TextField
            label="Product description (optional)"
            name="description"
            maxLength={8000}
            defaultValue={product?.description}
          />
          <TextField
            label="Reason for this revision"
            name="change_reason"
            required
            maxLength={1000}
            defaultValue={id ? "" : "Initial product record"}
          />
          <p className="quiet">
            SKU is unique within your organization and remains stable. If
            someone edits this record while you work, reload before submitting a
            fresh change.
          </p>
        </MutationForm>
      </section>
    </>
  );
}
export function ProductEditorPage({ org, id }: { org: string; id?: string }) {
  return (
    <TenantFrame key={`${org}/${id ?? "new"}`} org={org}>
      <ProductEditor org={org} id={id} />
    </TenantFrame>
  );
}
