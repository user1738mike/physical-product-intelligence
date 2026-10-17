"use client";

import { useEffect, useState } from "react";
import { request } from "../../lib/api";
import { importsApiPath, type ImportJob } from "../../lib/ingestion";
import { Field, MutationForm, messageFor } from "../products/ui";

type Policy = {
  version: number;
  minimum_days: number | null;
  legal_hold: boolean;
};
type Removal = {
  id: string;
  state: string;
  created_at: string;
  finished_at: string | null;
  reason: string;
};

export function RetentionSettings({
  org,
  owner,
}: {
  org: string;
  owner: boolean;
}) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [error, setError] = useState("");
  const path = importsApiPath(org) + "retention-policy/";
  useEffect(() => {
    let live = true;
    void request<Policy>(path)
      .then((value) => {
        if (live) setPolicy(value);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [path]);
  return (
    <section className="catalog-panel">
      <h2>Source retention</h2>
      <p>
        Original files are preserved by default. An owner may request removal of
        an unused failed or cancelled upload after the minimum age. Applied
        evidence, source hashes, review history and audit records are preserved.
        Backups retain their own approved schedule.
      </p>
      {error && <p role="alert">{error}</p>}
      {!policy ? (
        <p role="status">Loading retention policy…</p>
      ) : (
        <>
          <p>
            Legal hold: {policy.legal_hold ? "active" : "released"}. Minimum
            age:{" "}
            {policy.minimum_days === null
              ? "removal disabled"
              : `${policy.minimum_days} days`}
            . Policy version {policy.version}.
          </p>
          {owner && (
            <MutationForm
              key={policy.version}
              label="Save retention policy"
              action={async (data) => {
                setPolicy(
                  await request<Policy>(path, "PUT", {
                    expected_version: policy.version,
                    minimum_days:
                      String(data.get("days")).trim() === ""
                        ? null
                        : Number(data.get("days")),
                    legal_hold: data.get("hold") === "on",
                    reason: String(data.get("reason")),
                  }),
                );
              }}
            >
              <Field
                label="Minimum retention age in days (blank disables removal)"
                name="days"
                type="number"
                min={1}
                max={36500}
                defaultValue={policy.minimum_days ?? ""}
              />
              <label>
                <input
                  type="checkbox"
                  name="hold"
                  defaultChecked={policy.legal_hold}
                />{" "}
                Legal hold: preserve all original files
              </label>
              <Field
                label="Retention policy change reason"
                name="reason"
                required
                minLength={5}
                maxLength={1000}
              />
              <p>
                Saving a policy does not remove files. Each eligible source
                needs a separate owner request. Changing a policy invalidates
                pending requests.
              </p>
            </MutationForm>
          )}
        </>
      )}
    </section>
  );
}

export function SourceRemoval({
  org,
  job,
  owner,
  reload,
}: {
  org: string;
  job: ImportJob;
  owner: boolean;
  reload: () => void;
}) {
  const [items, setItems] = useState<Removal[] | null>(null);
  const [error, setError] = useState("");
  const path = importsApiPath(org) + job.id + "/source-removal/";
  const refresh = async () => setItems(await request<Removal[]>(path));
  useEffect(() => {
    let live = true;
    void request<Removal[]>(path)
      .then((value) => {
        if (live) setItems(value);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [path]);
  if (job.mode === "ai") return null;
  return (
    <section className="catalog-panel">
      <h2>Original source file</h2>
      <p>
        File status:{" "}
        {(job.source_file_state ?? "retained").replaceAll("_", " ")}. Source
        metadata and history remain available after removal.
      </p>
      {error && <p role="alert">{error}</p>}
      {!items ? (
        <p role="status">Loading removal history…</p>
      ) : (
        <>
          {items.map((item) => (
            <p key={item.id}>
              {item.state.replaceAll("_", " ")} · Requested{" "}
              {new Date(item.created_at).toLocaleString()} · {item.reason}
            </p>
          ))}
          <MutationForm
            label="Refresh source file status"
            action={async () => {
              await refresh();
              reload();
            }}
          >
            <p>
              Queued requests are checked by the maintenance processor. An
              uncertain outcome requires operator reconciliation.
            </p>
          </MutationForm>
          {owner &&
            ["failed", "cancelled"].includes(job.status) &&
            !items.some((item) => item.state !== "cancelled") && (
              <MutationForm
                label="Request unused source removal"
                action={async (data) => {
                  await request<Removal>(path, "POST", {
                    expected_version: job.version,
                    reason: String(data.get("reason")),
                  });
                  await refresh();
                  reload();
                }}
              >
                <p>
                  This permanently removes only the original file if retention
                  age, legal hold and provenance checks allow it. Files
                  supporting applied evidence cannot be removed.
                </p>
                <Field
                  label="Source removal reason"
                  name="reason"
                  required
                  minLength={5}
                  maxLength={1000}
                />
                <label>
                  <input type="checkbox" required /> I confirm permanent removal
                  of this unused original file.
                </label>
              </MutationForm>
            )}
        </>
      )}
    </section>
  );
}
