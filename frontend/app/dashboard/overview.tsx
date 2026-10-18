"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  dashboard,
  loadDashboardResource,
  type Dashboard,
  type DashboardResource,
} from "../../lib/dashboard";
import { commercial, type Commercial } from "../../lib/commercial";
import { integrations, type Integrations } from "../../lib/integrations";
import { messageFor, useTenant } from "../products/ui";

function useResource<T>(scope: string, read: () => Promise<T>, enabled = true) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<DashboardResource<T>>({
    scope,
    status: "loading",
  });
  useEffect(() => {
    if (!enabled) return;
    const task = loadDashboardResource(scope, read, setState, messageFor);
    return task.cancel;
  }, [scope, read, attempt, enabled]);
  return {
    state:
      state.scope === scope && enabled
        ? state
        : ({ scope, status: "loading" } as DashboardResource<T>),
    retry: () => setAttempt((value) => value + 1),
  };
}

const date = (value: string) =>
  new Date(value)
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d+Z$/, " UTC");
const label = (value: string) => value.replaceAll("_", " ");

function SummaryCard({
  title,
  href,
  children,
}: {
  title: string;
  href: string;
  children: ReactNode;
}) {
  return (
    <section className="dashboard-summary-card">
      <h2>
        <Link href={href}>{title}</Link>
      </h2>
      {children}
    </section>
  );
}

function OptionalRegion<T>({
  title,
  state,
  retry,
  children,
}: {
  title: string;
  state: DashboardResource<T>;
  retry: () => void;
  children: (data: T) => ReactNode;
}) {
  return (
    <section className="dashboard-panel" aria-label={title}>
      <h2>{title}</h2>
      {state.status === "loading" ? (
        <p role="status">Loading {title.toLowerCase()}…</p>
      ) : state.status === "error" ? (
        <>
          <p role="alert">Unavailable: {state.error}</p>
          <button type="button" onClick={retry}>
            Retry {title.toLowerCase()}
          </button>
        </>
      ) : (
        <>
          {children(state.data)}
          <button type="button" onClick={retry}>
            Refresh {title.toLowerCase()}
          </button>
        </>
      )}
    </section>
  );
}

export function OverviewDetails({
  data,
  plan,
  delivery,
  refreshPlan,
  refreshDelivery,
}: {
  data: Dashboard;
  plan: DashboardResource<Commercial>;
  delivery: DashboardResource<Integrations>;
  refreshPlan: () => void;
  refreshDelivery: () => void;
}) {
  const root = `/organizations/${encodeURIComponent(data.organization.id)}`;
  const manager = data.role !== "member";
  const workUnavailable =
    !data.organization.is_active ||
    (manager && plan.status === "ready" && plan.data.status !== "active");
  return (
    <>
      <p>
        {data.organization.name} · Your role: <strong>{data.role}</strong> ·
        Organization {data.organization.is_active ? "active" : "inactive"}
      </p>
      <p className="dashboard-scope">
        All-time totals, including archived records where labeled. Updated{" "}
        <time dateTime={data.generated_at}>{date(data.generated_at)}</time>.
      </p>
      <div className="dashboard-summary-grid">
        <SummaryCard title="Products" href={`${root}/products`}>
          <p>
            <strong>{data.products.total}</strong> total products
          </p>
          <p>
            {data.products.active} active · {data.products.archived} archived
          </p>
        </SummaryCard>
        <SummaryCard title="Imports and review" href={`${root}/imports`}>
          <p>
            <strong>{data.imports.attention}</strong> imports needing attention
          </p>
          <p>
            {data.imports.awaiting_review} awaiting review ·{" "}
            {data.imports.by_status.failed ?? 0} failed ·{" "}
            {data.imports.by_status.completed_with_errors ?? 0} completed with
            errors
          </p>
          <p>{data.imports.total} total imports, all statuses</p>
        </SummaryCard>
        <SummaryCard title="Equipment and rules" href={`${root}/equipment`}>
          <p>
            <strong>{data.equipment.total}</strong> equipment profiles
          </p>
          <p>
            {data.equipment.active} active · {data.equipment.draft} draft ·{" "}
            {data.equipment.archived} archived
          </p>
          <p>
            {data.equipment.active_with_activated_rules} active profiles with
            activated rules for their current specification
          </p>
        </SummaryCard>
        <SummaryCard title="Assessments" href={`${root}/assessments`}>
          <p>
            <strong>{data.assessments.total}</strong> assessments, all time
          </p>
          <p>
            {data.assessments.compatible} compatible ·{" "}
            {data.assessments.incompatible} incompatible ·{" "}
            {data.assessments.indeterminate} indeterminate
          </p>
        </SummaryCard>
      </div>
      <section className="dashboard-panel" aria-label="Quick actions">
        <h2>Quick actions</h2>
        {workUnavailable ? (
          <p>
            New work is unavailable with the current access status. Existing
            records remain available according to your permissions.
          </p>
        ) : (
          <>
            <div className="dashboard-actions">
              <Link href={`${root}/products/new`}>Add product</Link>
              <Link href={`${root}/imports`}>Upload evidence</Link>
              {manager && (
                <Link href={`${root}/equipment`}>Configure equipment</Link>
              )}
              <Link href={`${root}/assessments`}>Run assessment</Link>
            </div>
            <p>
              Availability and remaining allowances are checked in each section.
            </p>
          </>
        )}
      </section>
      <div className="dashboard-columns">
        <section className="dashboard-panel" aria-label="Recent imports">
          <h2>Recent imports</h2>
          <p>Up to five latest imports, all statuses.</p>
          {data.imports.recent.length === 0 ? (
            <p>No imports yet. Upload a source to begin review.</p>
          ) : (
            <ul className="record-list">
              {data.imports.recent.map((item) => (
                <li key={item.id}>
                  <Link href={`${root}/imports/${encodeURIComponent(item.id)}`}>
                    {item.display_name}
                  </Link>
                  <p>
                    {label(item.status)} ·{" "}
                    <time dateTime={item.created_at}>
                      {date(item.created_at)}
                    </time>
                  </p>
                </li>
              ))}
            </ul>
          )}
          <Link href={`${root}/imports`}>View all imports</Link>
        </section>
        <section className="dashboard-panel" aria-label="Recent assessments">
          <h2>Recent assessments</h2>
          <p>Up to five latest recorded results, all outcomes.</p>
          {data.assessments.recent.length === 0 ? (
            <p>No assessments yet. Select a product and equipment to begin.</p>
          ) : (
            <ul className="record-list">
              {data.assessments.recent.map((item) => (
                <li key={item.id}>
                  <Link
                    href={`${root}/assessments/${encodeURIComponent(item.id)}`}
                  >
                    {item.summary || `Assessment: ${label(item.overall)}`}
                  </Link>
                  <p>
                    {label(item.overall)} ·{" "}
                    <time dateTime={item.created_at}>
                      {date(item.created_at)}
                    </time>
                  </p>
                </li>
              ))}
            </ul>
          )}
          <Link href={`${root}/assessments`}>View assessment history</Link>
        </section>
      </div>
      {manager && (
        <div className="dashboard-columns">
          <OptionalRegion
            title="Plan and usage"
            state={plan}
            retry={refreshPlan}
          >
            {(value) => (
              <>
                <p>{value.plan?.name ?? "No plan assigned"}</p>
                <p>
                  Access: <strong>{value.status}</strong>
                </p>
                <p>
                  Usage period: {date(value.period_start)} to{" "}
                  {date(value.period_end)} (end excluded).
                </p>
                <ul>
                  {Object.entries(value.meters).map(([key, meter]) => (
                    <li key={key}>
                      {label(key)}: {meter.used} used, {meter.reserved}{" "}
                      reserved,{" "}
                      {meter.remaining === null ? "unlimited" : meter.remaining}{" "}
                      remaining
                    </li>
                  ))}
                </ul>
                {!value.historical_usage_complete && (
                  <p>
                    Earlier usage is incomplete; totals cover recorded metering.
                  </p>
                )}
                <p>
                  Access is assigned manually. No payments are collected here.
                </p>
                <Link href={`${root}/commercial`}>View plan and usage</Link>
              </>
            )}
          </OptionalRegion>
          <OptionalRegion
            title="Integration deliveries"
            state={delivery}
            retry={refreshDelivery}
          >
            {(value) => (
              <>
                <p>
                  Outbound delivery is currently{" "}
                  {value.outbound_available ? "available" : "unavailable"}.
                </p>
                {value.deliveries.length === 0 ? (
                  <p>No deliveries in the available history.</p>
                ) : (
                  <>
                    <p>
                      {
                        value.deliveries.filter((item) =>
                          ["retryable", "terminal", "paused"].includes(
                            item.state,
                          ),
                        ).length
                      }{" "}
                      need attention among the {value.deliveries.length} latest
                      deliveries returned (maximum 100).
                    </p>
                    <p>
                      Attention includes retryable, terminal and paused
                      deliveries.
                    </p>
                  </>
                )}
                <Link href={`${root}/integrations`}>Review integrations</Link>
              </>
            )}
          </OptionalRegion>
        </div>
      )}
    </>
  );
}

export default function DashboardOverview({ org }: { org: string }) {
  const tenant = useTenant();
  const scope = JSON.stringify([
    org,
    tenant.id,
    tenant.role,
    tenant.organization.is_active,
  ]);
  const read = useCallback(() => dashboard(org), [org]);
  const readPlan = useCallback(() => commercial(org), [org]);
  const readDelivery = useCallback(() => integrations(org), [org]);
  const overview = useResource(scope, read);
  const authorized =
    tenant.role !== "member" &&
    overview.state.status === "ready" &&
    overview.state.data.role !== "member";
  const optionalScope = `${scope}:${overview.state.status}`;
  const plan = useResource(optionalScope, readPlan, authorized);
  const delivery = useResource(optionalScope, readDelivery, authorized);
  return (
    <section className="dashboard-overview">
      <div className="page-heading">
        <div>
          <p className="eyebrow">ORGANIZATION WORKSPACE</p>
          <h1>Overview</h1>
        </div>
        <button type="button" onClick={overview.retry}>
          {overview.state.status === "error"
            ? "Retry overview"
            : "Refresh overview"}
        </button>
      </div>
      {overview.state.status === "loading" ? (
        <p role="status">Loading organization overview…</p>
      ) : overview.state.status === "error" ? (
        <section className="notice error">
          <h2>Overview unavailable</h2>
          <p role="alert">{overview.state.error}</p>
          <Link href="/products">Choose an organization</Link>
        </section>
      ) : (
        <OverviewDetails
          data={overview.state.data}
          plan={plan.state}
          delivery={delivery.state}
          refreshPlan={plan.retry}
          refreshDelivery={delivery.retry}
        />
      )}
    </section>
  );
}
