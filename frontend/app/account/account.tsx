"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  type Membership,
  type Organization,
  type User,
} from "../../lib/api";
import { mergeMemberships } from "../../lib/memberships";
import AuthForm from "./auth-form";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "authenticated"; user: User };

export default function Account() {
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [membershipPage, setMembershipPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [organization, setOrganization] = useState<Organization | null>(null);
  const feedback = useRef<HTMLParagraphElement>(null);

  async function loadMemberships(page = 1) {
    const result = await api.memberships(page);
    setMemberships((current) =>
      page === 1 ? result.results : mergeMemberships(current, result.results),
    );
    setMembershipPage(page);
    setHasMore(result.next !== null);
  }

  async function refresh() {
    setAuth({ status: "loading" });
    setMessage("");
    try {
      const user = await api.me();
      await loadMemberships();
      setAuth({ status: "authenticated", user });
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setAuth({ status: "anonymous" });
        setMemberships([]);
        setSelectedId("");
        setOrganization(null);
      } else {
        setAuth({ status: "error" });
        setMessage("Could not reach your account. Try again.");
      }
    }
  }

  useEffect(() => {
    void refresh();
  }, []);
  useEffect(() => {
    if (message) feedback.current?.focus();
  }, [message]);

  async function act(operation: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await operation();
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "Connection failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  function authenticate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const username = String(data.get("username"));
    const password = String(data.get("password"));
    // Remove passwords from the form before any request settles.
    const passwordInput = form.elements.namedItem(
      "password",
    ) as HTMLInputElement;
    passwordInput.value = "";
    void act(async () => {
      if (register) await api.register(username, password);
      await api.login(username, password);
      await refresh();
    });
  }

  function createOrganization(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (auth.status !== "authenticated") return;
    const currentUserId = auth.user.id;
    const form = event.currentTarget;
    const data = new FormData(form);
    void act(async () => {
      const created = await api.createOrganization(
        String(data.get("name")),
        String(data.get("slug")),
      );
      await loadMemberships();
      const members = await api.members(created.id);
      const membership = members.results.find(
        (item) => item.user.id === currentUserId,
      );
      if (!membership) {
        throw new ApiError(
          403,
          "Organization created, but your membership could not be refreshed.",
        );
      }
      setMemberships((current) =>
        mergeMemberships(current, [{ ...membership, organization: created }]),
      );
      setSelectedId(created.id);
      setOrganization(created);
      form.reset();
      setMessage(`Organization created. Your role: ${membership.role}.`);
    });
  }

  const selectedMembership = memberships.find(
    (item) => item.organization.id === selectedId,
  );

  return (
    <main className="account-shell">
      <header className="masthead">
        <Link href="/" className="brand">
          Physical Product Intelligence Cloud
        </Link>
        {auth.status === "authenticated" && (
          <button
            disabled={busy}
            onClick={() =>
              void act(async () => {
                await api.logout();
                await refresh();
              })
            }
          >
            Sign out
          </button>
        )}
      </header>
      <h1 className="account-title">Account &amp; organizations</h1>
      <p ref={feedback} role="status" aria-live="polite" tabIndex={-1}>
        {message}
      </p>
      {auth.status === "loading" && <p role="status">Loading your account…</p>}
      {auth.status === "error" && (
        <button onClick={() => void refresh()}>Try again</button>
      )}
      {auth.status === "anonymous" && (
        <AuthForm
          register={register}
          busy={busy}
          onSubmit={authenticate}
          onToggle={() => {
            setRegister(!register);
            setMessage("");
          }}
        />
      )}
      {auth.status === "authenticated" && (
        <>
          <p>
            Signed in as <strong>{auth.user.username}</strong>.
          </p>
          <section
            className="account-panel"
            aria-labelledby="organizations-title"
          >
            <h2 id="organizations-title">Your organizations</h2>
            {memberships.length === 0 ? (
              <p>You have no memberships yet.</p>
            ) : (
              <>
                <label htmlFor="organization">Active organization</label>
                <select
                  id="organization"
                  value={selectedId}
                  disabled={busy}
                  onChange={(event) => {
                    const id = event.target.value;
                    setSelectedId(id);
                    setOrganization(null);
                    if (id)
                      void act(async () => {
                        setOrganization(await api.organization(id));
                      });
                  }}
                >
                  <option value="">Choose an organization</option>
                  {memberships.map((item) => (
                    <option key={item.id} value={item.organization.id}>
                      {item.organization.name} ({item.role})
                      {item.organization.is_active ? "" : " — suspended"}
                    </option>
                  ))}
                </select>
                {hasMore && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void act(() => loadMemberships(membershipPage + 1))
                    }
                  >
                    Load more organizations
                  </button>
                )}
                {organization && (
                  <p>
                    Current organization: <strong>{organization.name}</strong>.
                    Your role:{" "}
                    {selectedMembership?.role ?? "refresh your memberships"}.
                  </p>
                )}
                {selectedMembership?.organization.is_active === false && (
                  <p>
                    This organization is suspended. Protected organization
                    access is unavailable.
                  </p>
                )}
              </>
            )}
          </section>
          <section className="account-panel" aria-labelledby="create-title">
            <h2 id="create-title">Create an organization</h2>
            <form onSubmit={createOrganization}>
              <label htmlFor="org-name">Organization name</label>
              <input id="org-name" name="name" required maxLength={160} />
              <label htmlFor="slug">Unique slug</label>
              <input
                id="slug"
                name="slug"
                required
                maxLength={80}
                pattern="[a-z0-9]+(-[a-z0-9]+)*"
                aria-describedby="slug-help"
              />
              <p id="slug-help">
                Lowercase letters, numbers and single hyphens. The slug cannot
                be changed.
              </p>
              <button type="submit" disabled={busy}>
                {busy ? "Please wait…" : "Create organization"}
              </button>
            </form>
          </section>
          <p>
            Product ingestion and assessment workflows are not yet available.
          </p>
        </>
      )}
    </main>
  );
}
