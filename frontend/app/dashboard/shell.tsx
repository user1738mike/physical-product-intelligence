"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, type Membership, type User } from "../../lib/api";
import { mergeMemberships } from "../../lib/memberships";
import {
  currentSection,
  organizationPath,
  visibleSections,
} from "../../lib/workspace";
import { TenantContext, WorkspaceContext } from "./context";

type Access = {
  org: string;
  path: string;
  user: User;
  membership: Membership;
};

export default function WorkspaceShell({
  org,
  children,
}: {
  org: string;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [access, setAccess] = useState<Access | null>(null);
  const [choices, setChoices] = useState<Membership[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [choiceError, setChoiceError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [switching, setSwitching] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const wasDrawerOpen = useRef(false);
  const sequence = useRef(0);
  const section = currentSection(pathname);
  const membership = access?.org === org ? access.membership : null;

  useEffect(() => {
    let live = true;
    async function validate() {
      const ticket = ++sequence.current;
      try {
        const [user, first] = await Promise.all([api.me(), api.memberships()]);
        let rows = first.results;
        let result = first;
        let number = 1;
        let found = rows.find((item) => item.organization.id === org);
        while (!found && result.next) {
          result = await api.memberships(++number);
          rows = mergeMemberships(rows, result.results);
          found = rows.find((item) => item.organization.id === org);
        }
        if (!found)
          throw new ApiError(
            404,
            "Organization access is unavailable. Choose another organization or check your membership.",
          );
        if (!live || ticket !== sequence.current) return;
        setAccess({ org, path: pathname, user, membership: found });
        setChoices(rows);
        setPage(number);
        setHasMore(result.next !== null);
        setError("");
      } catch (failure) {
        if (!live || ticket !== sequence.current) return;
        setAccess(null);
        setChoices([]);
        setError(
          failure instanceof ApiError
            ? failure.message
            : "Could not verify organization access. Please retry.",
        );
      }
    }
    void validate();
    const onFocus = () => {
      void validate();
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") void validate();
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener("ppi:access-refresh", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      live = false;
      sequence.current++;
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("ppi:access-refresh", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [org, pathname, attempt]);

  useEffect(() => {
    if (!drawer) {
      if (wasDrawerOpen.current) menuButton.current?.focus();
      wasDrawerOpen.current = false;
      return;
    }
    closeButton.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        wasDrawerOpen.current = true;
        setDrawer(false);
        menuButton.current?.focus();
      }
      if (event.key !== "Tab") return;
      const targets = sidebar.current?.querySelectorAll<HTMLElement>(
        "a[href], button:not([disabled])",
      );
      if (!targets?.length) return;
      const first = targets[0],
        last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const onResize = () => {
      if (window.matchMedia("(min-width: 1000px)").matches) setDrawer(false);
    };
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
    };
  }, [drawer]);

  async function loadMore() {
    const ticket = sequence.current;
    setLoadingMore(true);
    setChoiceError("");
    try {
      const result = await api.memberships(page + 1);
      if (ticket !== sequence.current) return;
      setChoices((current) => mergeMemberships(current, result.results));
      setPage(page + 1);
      setHasMore(result.next !== null);
    } catch {
      if (ticket === sequence.current)
        setChoiceError(
          "Could not load more organizations. Retry the same action.",
        );
    } finally {
      setLoadingMore(false);
    }
  }

  async function signOut() {
    setSigningOut(true);
    sequence.current++;
    setAccess(null);
    setChoices([]);
    setError("");
    try {
      await api.logout();
      router.replace("/account");
      router.refresh();
    } catch {
      setError("Sign out did not complete. Please retry sign out.");
      setSigningOut(false);
    }
  }

  const closeDrawer = () => {
    wasDrawerOpen.current = true;
    setDrawer(false);
    menuButton.current?.focus();
  };
  const ready =
    membership && access?.path === pathname && !switching && !signingOut;
  return (
    <div className="dashboard-shell" data-workspace-org={org}>
      <a className="skip-link" href="#workspace-main">
        Skip to workspace
      </a>
      {drawer && (
        <button
          className="dashboard-backdrop"
          aria-label="Dismiss navigation"
          onClick={closeDrawer}
          tabIndex={-1}
        />
      )}
      <aside
        ref={sidebar}
        id="organization-sidebar"
        className={`dashboard-sidebar${drawer ? " is-open" : ""}`}
        role={drawer ? "dialog" : undefined}
        aria-modal={drawer ? true : undefined}
        aria-label={drawer ? "Organization menu" : undefined}
      >
        <Link
          href={organizationPath(org)}
          className="brand dashboard-brand"
          onClick={() => setDrawer(false)}
        >
          <span className="mark" aria-hidden="true">
            P
          </span>
          <span>
            PHYSICAL PRODUCT
            <br />
            INTELLIGENCE CLOUD
          </span>
        </Link>
        <button
          className="dashboard-close secondary"
          ref={closeButton}
          aria-label="Close navigation"
          onClick={closeDrawer}
        >
          Close ×
        </button>
        <p className="dashboard-nav-label">WORKSPACE</p>
        <nav aria-label="Organization navigation">
          {membership &&
            visibleSections(membership.role).map((item) => (
              <Link
                key={item.path}
                href={organizationPath(org, item.path)}
                aria-current={section.path === item.path ? "page" : undefined}
                onClick={() => setDrawer(false)}
              >
                <span className="dashboard-nav-dot" aria-hidden="true" />
                {item.label}
              </Link>
            ))}
        </nav>
        <div className="dashboard-sidebar-footer">
          <span>Evidence-backed decisions.</span>
          <p>
            Assessments support handling decisions. Physical safety is not
            certified.
          </p>
          <Link href="/products">Choose an organization</Link>
        </div>
      </aside>
      <div className="dashboard-body" inert={drawer ? true : undefined}>
        <header className="dashboard-header">
          <div className="dashboard-header-page">
            <button
              className="dashboard-menu secondary"
              ref={menuButton}
              aria-label="Open navigation"
              aria-expanded={drawer}
              aria-controls="organization-sidebar"
              onClick={() => setDrawer(true)}
            >
              ☰
            </button>
            <div>
              <span className="dashboard-header-caption">
                Organization workspace
              </span>
              <strong>{section.label}</strong>
            </div>
          </div>
          <div className="dashboard-header-tools">
            <div className="dashboard-switcher">
              <label htmlFor="workspace-organization">
                Active organization
              </label>
              <select
                id="workspace-organization"
                value={membership ? org : ""}
                disabled={!membership || switching || signingOut}
                onChange={(event) => {
                  const id = event.target.value;
                  if (
                    id === org ||
                    !choices.some((item) => item.organization.id === id)
                  )
                    return;
                  sequence.current++;
                  setSwitching(true);
                  setDrawer(false);
                  router.push(organizationPath(id));
                }}
              >
                {!membership && (
                  <option value="">Choose an organization</option>
                )}
                {choices.map((item) => (
                  <option key={item.id} value={item.organization.id}>
                    {item.organization.name} ({item.role})
                    {item.organization.is_active ? "" : " — suspended"}
                  </option>
                ))}
              </select>
              {hasMore && (
                <button
                  className="dashboard-more"
                  disabled={loadingMore || switching}
                  onClick={() => void loadMore()}
                >
                  {loadingMore ? "Loading…" : "Load more organizations"}
                </button>
              )}
            </div>
            <Link
              href="/account"
              aria-label="Account"
              className="dashboard-account"
            >
              Account{access && <small>{access.user.username}</small>}
            </Link>
            <button
              className="secondary"
              disabled={signingOut}
              onClick={() => void signOut()}
            >
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>
        <main className="dashboard-main" id="workspace-main" tabIndex={-1}>
          {choiceError && (
            <p role="alert" className="notice error">
              {choiceError}
            </p>
          )}
          {error ? (
            <section className="notice error" role="alert">
              <h1>Access unavailable</h1>
              <p>{error}</p>
              <Link href="/products">Choose an organization</Link>
              <Link href="/account">Account / Sign in</Link>
              <button onClick={() => setAttempt((value) => value + 1)}>
                Retry access
              </button>
            </section>
          ) : !ready ? (
            <p role="status" className="loading">
              {switching
                ? "Opening organization…"
                : signingOut
                  ? "Signing out…"
                  : "Loading your organization…"}
            </p>
          ) : (
            <WorkspaceContext.Provider value={{ org }}>
              <TenantContext.Provider value={membership}>
                <div className="dashboard-context">
                  <span>{membership.organization.name}</span>
                  <span className="badge">{membership.role}</span>
                  {!membership.organization.is_active && (
                    <span className="badge unknown">
                      Suspended organization
                    </span>
                  )}
                </div>
                <div
                  key={`${org}:${access.user.id}:${membership.role}:${membership.organization.is_active}`}
                  className="dashboard-content"
                >
                  {children}
                </div>
              </TenantContext.Provider>
            </WorkspaceContext.Provider>
          )}
        </main>
      </div>
    </div>
  );
}
