"use client";

import Link from "next/link";
import {
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type InputHTMLAttributes,
} from "react";
import { ApiError } from "../../lib/api";
import { TenantContext, WorkspaceContext } from "../dashboard/context";
import WorkspaceShell from "../dashboard/shell";
import { organizationPath } from "../../lib/workspace";

export const messageFor = (error: unknown) =>
  error instanceof ApiError
    ? error.message
    : "Connection failed. Please try again.";
export { useTenant } from "../dashboard/context";

export function TenantFrame({
  org,
  children,
  allowInactiveOrganization = false,
}: {
  org: string;
  children: ReactNode;
  allowInactiveOrganization?: boolean;
}) {
  const workspace = useContext(WorkspaceContext);
  const membership = useContext(TenantContext);
  if (!workspace || workspace.org !== org) {
    return (
      <WorkspaceShell org={org}>
        <TenantFrame
          org={org}
          allowInactiveOrganization={allowInactiveOrganization}
        >
          {children}
        </TenantFrame>
      </WorkspaceShell>
    );
  }
  if (!membership) return <p role="status">Loading your organization…</p>;
  if (!membership.organization.is_active && !allowInactiveOrganization) {
    return (
      <section className="notice">
        <h1>Organization suspended</h1>
        <p>
          Business records are unavailable while this organization is suspended.
          Existing account and authorized management paths remain available.
        </p>
        <Link href={organizationPath(org, "settings")}>
          Organization settings
        </Link>
      </section>
    );
  }
  return <>{children}</>;
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
