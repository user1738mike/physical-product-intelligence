"use client";

import { useEffect, useState } from "react";
import { commercial, type Commercial } from "../../lib/commercial";
import { messageFor, TenantFrame, useTenant } from "../products/ui";

const date = (value: string | null) =>
  value
    ? new Date(value).toISOString().replace("T", " ").replace(".000Z", " UTC")
    : "No scheduled end";
const labels = {
  active_products: "Active products",
  assessments: "Assessments",
  extractions: "Extraction jobs",
};

export function UsageDetails({ data }: { data: Commercial }) {
  return (
    <>
      <h1>Plan and usage</h1>
      <p>
        {data.plan
          ? `${data.plan.name} · version ${data.plan.version}`
          : "No plan assigned"}
      </p>
      <p>
        Access: <strong>{data.status}</strong>
      </p>
      {data.plan && (
        <p>
          Plan features:{" "}
          {Object.entries(data.plan.features)
            .map(
              ([key, enabled]) =>
                `${({ catalog_write: "Catalog editing", evidence_import: "Evidence imports", equipment_write: "Equipment editing", assessments: "Assessments", ai_extraction: "AI extraction" } as Record<string, string>)[key] ?? key}: ${enabled ? "included" : "not included"}`,
            )
            .join(" · ")}
        </p>
      )}
      {data.status !== "active" && (
        <p role="status">
          New work is unavailable. Existing records remain available according
          to your organization permissions.
        </p>
      )}
      <p>
        Access starts: {data.starts_at ? date(data.starts_at) : "Not assigned"}.
        Access ends: {date(data.ends_at)}.
      </p>
      <p>
        Monthly usage period: {date(data.period_start)} to{" "}
        {date(data.period_end)} (end excluded).
      </p>
      <div className="table-scroll">
        <table>
          <caption>Organization allowances</caption>
          <thead>
            <tr>
              <th>Allowance</th>
              <th>Limit</th>
              <th>Used</th>
              <th>In progress</th>
              <th>Remaining</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.meters).map(([key, meter]) => (
              <tr key={key}>
                <th scope="row">{labels[key as keyof typeof labels]}</th>
                <td>{meter.limit === null ? "Unlimited" : meter.limit}</td>
                <td>{meter.used}</td>
                <td>{meter.reserved}</td>
                <td>
                  {meter.remaining === null
                    ? "Unlimited"
                    : meter.remaining === 0
                      ? "Allowance exhausted"
                      : meter.remaining}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>How usage is counted</h2>
      {Object.entries(data.meters).map(([key, meter]) => (
        <p key={key}>
          <strong>{labels[key as keyof typeof labels]}:</strong>{" "}
          {meter.definition}
        </p>
      ))}
      <p>
        Metering started:{" "}
        {data.metering_started_at
          ? date(data.metering_started_at)
          : "Not started"}
        . Earlier usage is incomplete.
      </p>
      <p>
        Access is assigned manually. No payments are collected through this
        screen.
      </p>
      <h2>Plan history</h2>
      {data.history.length === 0 ? (
        <p>No assignments yet.</p>
      ) : (
        <ul>
          {data.history.map((item) => (
            <li key={item.id}>
              {item.plan_code} · version {item.plan_version} · {item.status} ·{" "}
              {date(item.starts_at)} to {date(item.ends_at)}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Workspace({ org }: { org: string }) {
  const tenant = useTenant();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ data?: Commercial; error?: string }>({});
  useEffect(() => {
    let live = true;
    let sequence = 0;
    async function load() {
      const request = ++sequence;
      setState({});
      try {
        const data = await commercial(org);
        if (live && request === sequence) setState({ data });
      } catch (error) {
        if (live && request === sequence)
          setState({ error: messageFor(error) });
      }
    }
    void load();
    const refresh = () => {
      void load();
    };
    window.addEventListener("focus", refresh);
    return () => {
      live = false;
      window.removeEventListener("focus", refresh);
    };
  }, [org, attempt]);
  if (tenant.role === "member")
    return (
      <section>
        <h1>Plan and usage</h1>
        <p role="alert">
          Only organization owners and administrators can view plan details.
        </p>
      </section>
    );
  return (
    <section className="account-panel">
      {state.error ? (
        <>
          <h1>Plan and usage</h1>
          <p role="alert">{state.error}</p>
        </>
      ) : state.data ? (
        <UsageDetails data={state.data} />
      ) : (
        <p role="status">Loading plan and usage…</p>
      )}
      <button onClick={() => setAttempt((value) => value + 1)}>
        Refresh plan and usage
      </button>
    </section>
  );
}

export default function PlanUsage({ org }: { org: string }) {
  return (
    <TenantFrame org={org} allowInactiveOrganization>
      <Workspace key={org} org={org} />
    </TenantFrame>
  );
}
