"use client";

import Link from "next/link";
import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type InputHTMLAttributes,
} from "react";
import { api, ApiError, type Membership } from "../../lib/api";
import { catalogPath } from "../../lib/products";

export const messageFor = (error: unknown) =>
  error instanceof ApiError
    ? error.message
    : "Connection failed. Please try again.";
const Tenant = createContext<Membership | null>(null);
export function useTenant() {
  const value = useContext(Tenant);
  if (!value) throw new Error("Organization context is missing");
  return value;
}

export function TenantFrame({
  org,
  children,
  allowInactiveOrganization = false,
}: {
  org: string;
  children: ReactNode;
  allowInactiveOrganization?: boolean;
}) {
  const [membership, setMembership] = useState<Membership | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    async function load() {
      await api.me();
      let page = 1;
      while (true) {
        const result = await api.memberships(page);
        const found = result.results.find(
          (item) => item.organization.id === org,
        );
        if (found) {
          const organization =
            allowInactiveOrganization && !found.organization.is_active
              ? found.organization
              : await api.organization(org);
          if (live) setMembership({ ...found, organization });
          return;
        }
        if (!result.next)
          throw new ApiError(
            404,
            "Organization access is unavailable. Check your membership or sign in.",
          );
        page++;
      }
    }
    setMembership(null);
    setError("");
    void load().catch((failure) => {
      if (live) setError(messageFor(failure));
    });
    return () => {
      live = false;
    };
  }, [org, attempt, allowInactiveOrganization]);
  return (
    <main className="catalog-shell">
      <header className="masthead">
        <Link href="/" className="brand">
          <span className="mark" aria-hidden="true">
            P
          </span>
          <span>
            PHYSICAL PRODUCT
            <br />
            INTELLIGENCE CLOUD
          </span>
        </Link>
        <nav aria-label="Workspace">
          <Link href="/products">Organizations</Link>
          <Link href={catalogPath(org)}>Catalog</Link>
          <Link href={`/organizations/${encodeURIComponent(org)}/imports`}>
            Imports
          </Link>
          <Link href={`/organizations/${encodeURIComponent(org)}/equipment`}>
            Equipment
          </Link>
          <Link href={`/organizations/${encodeURIComponent(org)}/assessments`}>
            Assessments
          </Link>
          <Link href="/account">Account</Link>
          {membership && membership.role !== "member" && (
            <Link
              href={`/organizations/${encodeURIComponent(org)}/integrations`}
            >
              Integrations
            </Link>
          )}
          {membership && membership.role !== "member" && (
            <Link href={`/organizations/${encodeURIComponent(org)}/commercial`}>
              Plan and usage
            </Link>
          )}
          {membership && membership.role !== "member" && (
            <Link href={`/organizations/${encodeURIComponent(org)}/billing`}>
              Billing history
            </Link>
          )}
        </nav>
      </header>
      {error ? (
        <section className="notice error" role="alert">
          <h1>Access unavailable</h1>
          <p>{error}</p>
          <Link href="/account">Sign in / manage memberships</Link>
          <button onClick={() => setAttempt(attempt + 1)}>Retry access</button>
        </section>
      ) : !membership ? (
        <p role="status" className="loading">
          Loading your organization…
        </p>
      ) : (
        <Tenant.Provider value={membership}>
          <div className="workspace-context">
            <span>{membership.organization.name}</span>
            <span>Your role: {membership.role}</span>
          </div>
          {children}
        </Tenant.Provider>
      )}
    </main>
  );
}

export function Field({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  const id = useId();
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <input id={id} {...props} />
    </label>
  );
}
export function TextField({
  label,
  name,
  defaultValue,
  required,
  maxLength = 2000,
  minLength,
}: {
  label: string;
  name: string;
  defaultValue?: string;
  required?: boolean;
  maxLength?: number;
  minLength?: number;
}) {
  const id = useId();
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <textarea
        id={id}
        name={name}
        defaultValue={defaultValue}
        required={required}
        maxLength={maxLength}
        minLength={minLength}
        rows={3}
      />
    </label>
  );
}
export function MutationForm({
  action,
  label,
  children,
  className = "",
  disabled = false,
}: {
  action: (data: FormData) => Promise<void>;
  label: string;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const feedback = useRef<HTMLParagraphElement>(null);
  const errorId = useId();
  useEffect(() => {
    if (error) feedback.current?.focus();
  }, [error]);
  return (
    <form
      className={`workflow-form ${className}`}
      aria-label={label}
      aria-describedby={error ? errorId : undefined}
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        setError("");
        setBusy(true);
        void action(data)
          .catch((failure) => setError(messageFor(failure)))
          .finally(() => setBusy(false));
      }}
    >
      {error && (
        <p
          className="notice error"
          role="alert"
          tabIndex={-1}
          ref={feedback}
          id={errorId}
        >
          {error}
        </p>
      )}
      <fieldset disabled={busy || disabled}>
        {children}
        <button type="submit">{busy ? "Saving…" : label}</button>
      </fieldset>
    </form>
  );
}
export function Pagination({
  page,
  count,
  hasNext,
  change,
}: {
  page: number;
  count: number;
  hasNext: boolean;
  change: (page: number) => void;
}) {
  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => change(page - 1)}
      >
        Previous
      </button>
      <span aria-live="polite">
        Page {page} · {count} records
      </span>
      <button
        type="button"
        disabled={!hasNext}
        onClick={() => change(page + 1)}
      >
        Next
      </button>
    </nav>
  );
}
export const text = (data: FormData, key: string) =>
  String(data.get(key) ?? "").trim();
export function observedTime(data: FormData) {
  return new Date(text(data, "observed_at")).toISOString();
}
