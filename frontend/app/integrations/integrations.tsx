"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  createCredential,
  integrations,
  replayDelivery,
  revokeCredential,
  rotateSigning,
  saveDestination,
  scopes,
  type Credential,
  type Destination,
  type Integrations,
} from "../../lib/integrations";
import { messageFor, TenantFrame, useTenant } from "../products/ui";

function Workspace({ org }: { org: string }) {
  const tenant = useTenant();
  const [data, setData] = useState<Integrations>();
  const [error, setError] = useState("");
  const [secret, setSecret] = useState("");
  const [secretKind, setSecretKind] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<string[]>([...scopes]);
  const [rotation, setRotation] = useState<Credential>();
  const [editing, setEditing] = useState<Destination>();
  const generation = useRef(0);
  useEffect(() => {
    let live = true;
    const sequence = ++generation.current;
    setBusy(false);
    setData(undefined);
    setSecret("");
    if (tenant.role !== "member")
      void integrations(org)
        .then((value) => {
          if (live && sequence === generation.current) {
            setData(value);
            setError("");
          }
        })
        .catch((reason) => {
          if (live && sequence === generation.current)
            setError(messageFor(reason));
        });
    const refresh = () => {
      setSecret("");
      setAttempt((value) => value + 1);
    };
    window.addEventListener("focus", refresh);
    return () => {
      live = false;
      generation.current++;
      window.removeEventListener("focus", refresh);
    };
  }, [org, attempt, tenant.role]);
  if (tenant.role === "member")
    return (
      <section>
        <h1>Integrations</h1>
        <p role="alert">
          Only organization owners and administrators can manage integrations.
        </p>
      </section>
    );
  async function mutate(action: () => Promise<unknown>) {
    if (busy) return;
    const sequence = generation.current;
    setBusy(true);
    setSecret("");
    setError("");
    try {
      const result = await action();
      if (sequence !== generation.current) return;
      const updated = await integrations(org);
      if (sequence !== generation.current) return;
      setData(updated);
      if (
        result &&
        typeof result === "object" &&
        "secret" in result &&
        typeof result.secret === "string"
      )
        setSecret(result.secret);
    } catch (reason) {
      if (sequence === generation.current) setError(messageFor(reason));
    } finally {
      if (sequence === generation.current) setBusy(false);
    }
  }
  function credentialSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setSecretKind("API credential");
    void mutate(() =>
      createCredential(org, {
        name: String(fields.get("name")),
        scopes: selected,
        expires_at: new Date(
          Date.now() + Number(fields.get("days")) * 86400000,
        ).toISOString(),
        ...(rotation
          ? { rotate: rotation.id, revoke_old: fields.get("overlap") !== "on" }
          : {}),
      }),
    );
    setRotation(undefined);
  }
  function destinationSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setSecretKind("Webhook signing secret");
    void mutate(() =>
      saveDestination(
        org,
        {
          url: String(fields.get("url")),
          subscriptions:
            fields.get("subscribed") === "on" ? ["assessment.completed"] : [],
          enabled: true,
          ...(editing ? { expected_revision: editing.revision } : {}),
        },
        editing?.id,
      ),
    );
    setEditing(undefined);
  }
  return (
    <section>
      <h1>Integrations</h1>
      <p>
        Read-only credentials connect your organization to trusted tools. Access
        ends when the credential expires, is revoked, or its issuer loses an
        authorized role.
      </p>
      {error && <p role="alert">{error}</p>}
      {secret && (
        <aside role="status" aria-label="One-time secret">
          <h2>{secretKind}</h2>
          <p>
            Save this secret securely now. It will not be shown again. Avoid
            screenshots or sharing it in messages.
          </p>
          <code aria-label="Secret value">{secret}</code>
          <p>
            <button onClick={() => setSecret("")}>
              I have saved the secret
            </button>
          </p>
        </aside>
      )}
      {!data ? (
        <p role="status">
          {error
            ? "Integration details are unavailable."
            : "Loading integrations…"}
        </p>
      ) : (
        <>
          <h2>API credentials</h2>
          <p>
            Active credential allowance: {data.allowances.credentials}. Enabled
            destination allowance: {data.allowances.destinations}.
          </p>
          {!data.credential_creation_available && (
            <p role="status">
              New API credentials are not available with your current access.
              You can still review and revoke existing credentials.
            </p>
          )}
          {data.credential_creation_available && (
            <form onSubmit={credentialSubmit} aria-label="Credential form">
              <label>
                Name{" "}
                <input
                  name="name"
                  required
                  maxLength={80}
                  defaultValue={rotation?.name ?? ""}
                  key={rotation?.id ?? "new"}
                />
              </label>
              <fieldset>
                <legend>Read-only scopes</legend>
                {scopes.map((scope) => (
                  <label key={scope}>
                    <input
                      type="checkbox"
                      checked={selected.includes(scope)}
                      onChange={(event) =>
                        setSelected((value) =>
                          event.target.checked
                            ? [...value, scope]
                            : value.filter((item) => item !== scope),
                        )
                      }
                    />
                    {scope}
                  </label>
                ))}
              </fieldset>
              <label>
                Expires in{" "}
                <select name="days" defaultValue="30">
                  <option value="7">7 days</option>
                  <option value="30">30 days</option>
                  <option value="89">89 days</option>
                </select>
              </label>
              {rotation && (
                <>
                  <p>
                    Rotating {rotation.name}. The previous credential is revoked
                    immediately by default.
                  </p>
                  <label>
                    <input type="checkbox" name="overlap" />
                    Keep the previous credential until its existing expiry
                  </label>
                </>
              )}
              <button disabled={busy || !selected.length}>
                {rotation ? "Rotate credential" : "Create credential"}
              </button>
              {rotation && (
                <button type="button" onClick={() => setRotation(undefined)}>
                  Cancel rotation
                </button>
              )}
            </form>
          )}
          {data.credentials.length === 0 && <p>No API credentials yet.</p>}
          {data.credentials.map((item) => (
            <article className="account-panel" key={item.id}>
              <h3>{item.name}</h3>
              <p>Scopes: {item.scopes.join(", ")}</p>
              <p>
                Expires: {item.expires_at} ·{" "}
                {item.revoked_at ? "Revoked" : "Active until expiry"}
              </p>
              <p>Last used: {item.last_used_at ?? "Not yet used"}</p>
              {!item.revoked_at && (
                <>
                  <button
                    disabled={busy}
                    onClick={() => {
                      setRotation(item);
                      setSecret("");
                      setSelected(item.scopes);
                    }}
                  >
                    Rotate {item.name}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      void mutate(() => revokeCredential(org, item.id))
                    }
                  >
                    Revoke {item.name}
                  </button>
                </>
              )}
            </article>
          ))}
          <h2>Webhook destinations</h2>
          {!data.outbound_available && (
            <p role="status">
              Outbound notifications are not available. You can still review
              existing destinations and delivery history.
            </p>
          )}
          {data.outbound_available && (
            <form
              onSubmit={destinationSubmit}
              aria-label="Destination form"
              key={editing?.id ?? "new-destination"}
            >
              <label>
                HTTPS destination{" "}
                <input
                  name="url"
                  type="url"
                  required
                  maxLength={500}
                  defaultValue={editing?.url ?? ""}
                  placeholder="https://approved.example/webhooks"
                />
              </label>
              <label>
                <input
                  name="subscribed"
                  type="checkbox"
                  defaultChecked={
                    editing
                      ? editing.subscriptions.includes("assessment.completed")
                      : true
                  }
                />
                Assessment completed
              </label>
              <button disabled={busy}>
                {editing ? "Update destination" : "Add destination"}
              </button>
              {editing && (
                <button type="button" onClick={() => setEditing(undefined)}>
                  Cancel edit
                </button>
              )}
            </form>
          )}
          {data.destinations.length === 0 && (
            <p>No webhook destinations yet.</p>
          )}
          {data.destinations.map((item) => (
            <article className="account-panel" key={item.id}>
              <h3>{item.url}</h3>
              <p>
                {item.enabled ? "Enabled" : "Disabled"} · revision{" "}
                {item.revision} · signing version {item.key_version}
              </p>
              <p>Events: {item.subscriptions.join(", ") || "None"}</p>
              {item.overlap_until && (
                <p>
                  Previous signing version accepted until {item.overlap_until}.
                </p>
              )}
              <button
                disabled={busy || !data.outbound_available}
                onClick={() => setEditing(item)}
              >
                Edit destination
              </button>
              <button
                disabled={busy || !item.enabled}
                onClick={() =>
                  void mutate(() =>
                    saveDestination(
                      org,
                      {
                        url: item.url,
                        subscriptions: item.subscriptions,
                        enabled: false,
                        expected_revision: item.revision,
                      },
                      item.id,
                    ),
                  )
                }
              >
                Disable destination
              </button>
              <button
                disabled={busy || !data.outbound_available}
                onClick={() => {
                  setSecretKind("Webhook signing secret");
                  void mutate(() => rotateSigning(org, item.id, false));
                }}
              >
                Rotate signing secret
              </button>
              <button
                disabled={busy || !data.outbound_available}
                onClick={() => {
                  setSecretKind("Webhook signing secret");
                  void mutate(() => rotateSigning(org, item.id, true));
                }}
              >
                Replace compromised signing secret
              </button>
            </article>
          ))}
          <h2>Recent deliveries</h2>
          <p>
            Up to 100 recent records. Notifications may arrive more than once;
            receivers must deduplicate by event ID.
          </p>
          {data.deliveries.length === 0 && <p>No deliveries yet.</p>}
          {data.deliveries.map((item) => (
            <article className="account-panel" key={item.id}>
              <h3>Event {item.event_id}</h3>
              <p>
                Status: {item.state} · attempts {item.attempts}
                {item.status_code ? ` · HTTP ${item.status_code}` : ""}
              </p>
              <p>{item.diagnostic.replaceAll("_", " ")}</p>
              <button
                disabled={
                  busy ||
                  item.state === "claimed" ||
                  item.replays >= 3 ||
                  !data.outbound_available
                }
                onClick={() => void mutate(() => replayDelivery(org, item.id))}
              >
                Replay delivery
              </button>
            </article>
          ))}
        </>
      )}
      <button disabled={busy} onClick={() => setAttempt((value) => value + 1)}>
        Refresh integrations
      </button>
    </section>
  );
}

export default function IntegrationsPage({ org }: { org: string }) {
  return (
    <TenantFrame org={org} allowInactiveOrganization>
      <Workspace org={org} key={org} />
    </TenantFrame>
  );
}
