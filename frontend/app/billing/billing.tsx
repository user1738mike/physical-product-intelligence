"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { billing, money, type Billing } from "../../lib/billing";
import { messageFor, TenantFrame, useTenant } from "../products/ui";

const label = (value: string) => value.replaceAll("_", " ");

export function BillingDetails({ data }: { data: Billing }) {
  return (
    <>
      <h1>Billing history</h1>
      {!data.collection_available && (
        <p role="status">
          Payment collection is not available. You can still review your
          internal statements and payment status.
        </p>
      )}
      <p>
        These are internal billing statements, not tax invoices. Confirmation
        may be delayed; refresh to check the latest status.
      </p>
      <h2>Statements</h2>
      {data.statements.length === 0 ? (
        <p>No statements yet.</p>
      ) : (
        data.statements.map((item) => (
          <article
            key={item.id}
            className="account-panel"
            aria-label={`Statement ${item.id}`}
          >
            <h3>Statement {item.id.slice(0, 8)}</h3>
            <p>
              Status: <strong>{label(item.status)}</strong> · Settlement:{" "}
              {label(item.settlement_status)}
            </p>
            <p>
              Period: {new Date(item.period_start).toISOString().slice(0, 10)}{" "}
              to {new Date(item.period_end).toISOString().slice(0, 10)} (end
              excluded).
            </p>
            <dl>
              <dt>Total</dt>
              <dd>{money(item.total_minor, item.currency, item.exponent)}</dd>
              <dt>Settled</dt>
              <dd>{money(item.settled_minor, item.currency, item.exponent)}</dd>
              <dt>Remaining</dt>
              <dd>
                {money(item.remaining_minor, item.currency, item.exponent)}
              </dd>
            </dl>
            <p>
              Access assignment:{" "}
              {item.access_fulfilled
                ? "Recorded"
                : "No change from this statement"}
            </p>
            {item.corrections.length > 0 && (
              <ul aria-label="Statement corrections">
                {item.corrections.map((c) => (
                  <li key={c.id}>
                    Correction:{" "}
                    {money(c.delta_minor, item.currency, item.exponent)} ·{" "}
                    {new Date(c.created_at).toISOString()}
                  </li>
                ))}
              </ul>
            )}
            {item.settlements.length > 0 && (
              <ul aria-label="Settlement history">
                {item.settlements.map((s) => (
                  <li key={s.id}>
                    {s.kind === "refund"
                      ? "Observed refund"
                      : "Payment allocation"}
                    : {money(s.amount_minor, item.currency, item.exponent)} ·{" "}
                    {new Date(s.created_at).toISOString()}
                  </li>
                ))}
              </ul>
            )}
            <a href={item.download_path}>Download internal statement</a>
          </article>
        ))
      )}
      <h2>Payment operations</h2>
      {data.operations.length === 0 ? (
        <p>No payment operations yet.</p>
      ) : (
        <ul>
          {data.operations.map((item) => (
            <li key={item.id}>
              Operation {item.id.slice(0, 8)}: {label(item.status)}.{" "}
              {item.status === "unknown"
                ? "The outcome needs review; do not start a duplicate request."
                : ""}{" "}
              Confirmation window ends {new Date(item.expires_at).toISOString()}
              .
            </li>
          ))}
        </ul>
      )}
      {Object.keys(data.unapplied_credit).length > 0 && (
        <section>
          <h2>Unapplied credit</h2>
          {Object.entries(data.unapplied_credit).map(([currency, minor]) => (
            <p key={currency}>
              {currency}: {minor} minor units awaiting allocation/review.
            </p>
          ))}
        </section>
      )}
    </>
  );
}

function Workspace({ org }: { org: string }) {
  const tenant = useTenant();
  const [attempt, setAttempt] = useState(0),
    [state, setState] = useState<{ data?: Billing; error?: string }>({});
  useEffect(() => {
    let live = true,
      sequence = 0;
    async function load() {
      const current = ++sequence;
      setState({});
      try {
        const data = await billing(org);
        if (live && sequence === current) setState({ data });
      } catch (error) {
        if (live && sequence === current)
          setState({ error: messageFor(error) });
      }
    }
    const refresh = () => {
      void load();
    };
    void load();
    window.addEventListener("focus", refresh);
    return () => {
      live = false;
      window.removeEventListener("focus", refresh);
    };
  }, [org, attempt]);
  if (tenant.role === "member")
    return (
      <section>
        <h1>Billing history</h1>
        <p role="alert">
          Only organization owners and administrators can view billing details.
        </p>
      </section>
    );
  return (
    <section>
      {state.error ? (
        <>
          <h1>Billing history</h1>
          <p role="alert">{state.error}</p>
        </>
      ) : state.data ? (
        <BillingDetails data={state.data} />
      ) : (
        <p role="status">Loading billing history…</p>
      )}
      <button onClick={() => setAttempt((x) => x + 1)}>
        Refresh billing history
      </button>
      <p>
        <Link href={`/organizations/${encodeURIComponent(org)}/commercial`}>
          Plan and usage
        </Link>
      </p>
    </section>
  );
}

export default function BillingPage({ org }: { org: string }) {
  return (
    <TenantFrame org={org} allowInactiveOrganization>
      <Workspace org={org} key={org} />
    </TenantFrame>
  );
}
