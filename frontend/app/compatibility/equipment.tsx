"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  compatibility,
  equipmentPath,
  type Equipment,
  type EquipmentDefinition,
  type EquipmentRevision,
  type Rule,
  type RuleSet,
} from "../../lib/compatibility";
import type { Page } from "../../lib/api";
import {
  Field,
  MutationForm,
  Pagination,
  TenantFrame,
  TextField,
  messageFor,
  text,
  useTenant,
} from "../products/ui";

const categories = [
  "conveyor",
  "storage",
  "tote_bin",
  "shelving",
  "picking_cell",
  "gripper",
  "handling",
];
const levels = ["unit", "inner", "case", "pallet"];
function DefinitionFields({
  definition,
}: {
  definition?: EquipmentDefinition;
}) {
  return (
    <>
      <Field
        label="Equipment name"
        name="name"
        defaultValue={definition?.name}
        maxLength={200}
        required
      />
      <div className="form-grid">
        <Field
          label="Manufacturer (unknown if blank)"
          name="manufacturer"
          defaultValue={definition?.manufacturer}
          maxLength={160}
        />
        <Field
          label="Model (unknown if blank)"
          name="model"
          defaultValue={definition?.model}
          maxLength={160}
        />
        <label className="field">
          Category
          <select
            name="category"
            defaultValue={definition?.category ?? ""}
            required
          >
            <option value="">Choose category</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
      </div>
      <TextField
        label="Description"
        name="description"
        defaultValue={definition?.description}
      />
      <TextField
        label="Operational context / intended workflow"
        name="operational_context"
        defaultValue={definition?.operational_context}
      />
      <Field
        label="Manufacturer document or specification reference"
        name="source_reference"
        defaultValue={definition?.source_reference}
        maxLength={1000}
      />
      <fieldset>
        <legend>
          Documented supported packaging levels (leave unknown if unspecified)
        </legend>
        {levels.map((level) => (
          <label className="check-field" key={level}>
            <input
              type="checkbox"
              name="supported_levels"
              value={level}
              defaultChecked={definition?.supported_levels.includes(level)}
            />
            {level}
          </label>
        ))}
      </fieldset>
      <TextField
        label="Orientation notes (descriptive; rules control evaluation)"
        name="orientation_notes"
        defaultValue={definition?.orientation_notes}
        maxLength={1000}
      />
      <TextField
        label="Handling restrictions / unmodeled considerations"
        name="handling_notes"
        defaultValue={definition?.handling_notes}
      />
    </>
  );
}
function definitionData(data: FormData) {
  return {
    ...Object.fromEntries(
      [
        "name",
        "description",
        "manufacturer",
        "model",
        "category",
        "source_reference",
        "operational_context",
        "orientation_notes",
        "handling_notes",
      ].map((key) => [key, text(data, key)]),
    ),
    supported_levels: data.getAll("supported_levels").map(String),
  };
}

export function EquipmentList({ org }: { org: string }) {
  return (
    <TenantFrame org={org}>
      <List org={org} />
    </TenantFrame>
  );
}
function List({ org }: { org: string }) {
  const { role } = useTenant(),
    manager = role !== "member";
  const [result, setResult] = useState<Page<Equipment> | null>(null),
    [error, setError] = useState("");
  const [page, setPage] = useState(1),
    [filters, setFilters] = useState({ search: "", status: "", category: "" });
  useEffect(() => {
    let live = true;
    void compatibility
      .equipment(org, { ...filters, page })
      .then((r) => {
        if (live) setResult(r);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, page, filters]);
  return (
    <>
      <h1>Equipment profiles</h1>
      <p>
        Document equipment constraints, preserve rule versions, and assess
        recorded product inputs. Unknown specifications stay unknown.
      </p>
      {error && <p role="alert">{error}</p>}
      <section className="catalog-panel">
        <MutationForm
          label="Filter equipment"
          action={async (data) => {
            setFilters({
              search: text(data, "search"),
              status: text(data, "status"),
              category: text(data, "category"),
            });
            setPage(1);
          }}
        >
          <Field label="Search code or name" name="search" maxLength={100} />
          <label className="field">
            Status
            <select name="status">
              <option value="">All statuses</option>
              {["draft", "active", "archived"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Category filter
            <select name="category">
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </MutationForm>
        {!result ? (
          <p role="status">Loading equipment…</p>
        ) : (
          <>
            <ul className="record-list">
              {result.results.map((e) => (
                <li key={e.id}>
                  <Link href={`${equipmentPath(org)}/${e.id}`}>
                    {e.definition.name}
                  </Link>{" "}
                  · {e.code} · {e.status} · specification {e.revision}
                </li>
              ))}
            </ul>
            {!result.count && <p>No equipment profiles match.</p>}
            <Pagination
              page={page}
              count={result.count}
              hasNext={!!result.next}
              change={setPage}
            />
          </>
        )}
      </section>
      {manager && (
        <section className="catalog-panel">
          <h2>Create equipment profile</h2>
          <MutationForm
            label="Create equipment draft"
            action={async (data) => {
              const result = await compatibility.createEquipment(org, {
                ...definitionData(data),
                code: text(data, "code"),
              });
              window.location.assign(`${equipmentPath(org)}/${result.id}`);
            }}
          >
            <Field
              label="Stable equipment code"
              name="code"
              maxLength={100}
              pattern="[A-Za-z0-9][A-Za-z0-9._-]*"
              required
            />
            <DefinitionFields />
          </MutationForm>
        </section>
      )}
    </>
  );
}

export function EquipmentDetail({ org, id }: { org: string; id: string }) {
  return (
    <TenantFrame org={org}>
      <Detail org={org} id={id} />
    </TenantFrame>
  );
}
function Detail({ org, id }: { org: string; id: string }) {
  const { role } = useTenant(),
    manager = role !== "member";
  const [profile, setProfile] = useState<Equipment | null>(null),
    [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0),
    [rulePage, setRulePage] = useState(1),
    [revisionPage, setRevisionPage] = useState(1);
  const [rules, setRules] = useState<Page<RuleSet> | null>(null),
    [revisions, setRevisions] = useState<Page<EquipmentRevision> | null>(null);
  const [seed, setSeed] = useState<RuleSet | null>(null);
  const reload = () => setRefresh((n) => n + 1);
  useEffect(() => {
    let live = true;
    void Promise.all([
      compatibility.profile(org, id),
      compatibility.rules(org, id, rulePage),
      compatibility.revisions(org, id, revisionPage),
    ])
      .then(([p, r, v]) => {
        if (live) {
          setProfile(p);
          setRules(r);
          setRevisions(v);
        }
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [org, id, refresh, rulePage, revisionPage]);
  if (error) return <p role="alert">{error}</p>;
  if (!profile) return <p role="status">Loading specification and rules…</p>;
  const d = profile.definition;
  return (
    <>
      <Link href={equipmentPath(org)}>Equipment list</Link>
      <h1>{d.name}</h1>
      <p>
        {profile.code} · {profile.status} · specification {profile.revision} ·
        edit version {profile.version}
      </p>
      <section className="catalog-panel">
        <h2>Documented configuration</h2>
        <p>{d.description || "Description unknown"}</p>
        <p>
          {d.manufacturer || "Manufacturer unknown"} ·{" "}
          {d.model || "Model unknown"} · {d.category}
        </p>
        <p>{d.operational_context || "Operational context unknown"}</p>
        <p>Supported levels: {d.supported_levels.join(", ") || "Unknown"}</p>
        <p>Specification reference: {d.source_reference || "Unknown"}</p>
        <p>
          Orientation:{" "}
          {d.orientation_notes || "No additional orientation notes"}
        </p>
        <p>
          Other restrictions:{" "}
          {d.handling_notes ||
            "No additional restrictions documented; this is not proof of their absence."}
        </p>
        <p>
          Numeric limits and executable orientation restrictions belong to the
          versioned rules below. Free text is never executed.
        </p>
        {manager && (
          <MutationForm
            label={
              profile.status === "archived"
                ? "Restore to draft"
                : "Archive equipment"
            }
            action={async (data) => {
              await compatibility.state(org, id, {
                expected_version: profile.version,
                status: profile.status === "archived" ? "draft" : "archived",
                reason: text(data, "reason"),
              });
              reload();
            }}
          >
            <Field
              label="Lifecycle reason"
              name="reason"
              minLength={5}
              required
            />
          </MutationForm>
        )}
      </section>
      {manager && profile.status !== "archived" && (
        <details className="catalog-panel">
          <summary>Edit equipment specification</summary>
          <p>
            Editing appends a specification revision and returns the profile to
            draft. Existing assessments retain their inputs.
          </p>
          <MutationForm
            key={profile.version}
            label="Save equipment revision"
            action={async (data) => {
              await compatibility.editEquipment(org, id, {
                ...definitionData(data),
                expected_version: profile.version,
                reason: text(data, "reason"),
              });
              reload();
            }}
          >
            <DefinitionFields definition={d} />
            <Field
              label="Specification change reason"
              name="reason"
              minLength={5}
              required
            />
          </MutationForm>
        </details>
      )}
      <section className="catalog-panel">
        <h2>Rule-set versions</h2>
        <p>
          Only activated sets bound to the current specification are eligible.
          Missing maximum length, width, height or mass creates an indeterminate
          coverage check.
        </p>
        {rules?.results.map((r) => (
          <article className="evidence-card" key={r.id}>
            <h3>
              {r.name} · version {r.number}
            </h3>
            <p>
              {r.activation ? "Activated" : "Draft"} · specification{" "}
              {r.equipment_revision_id === profile.revision_id
                ? "current"
                : "historical"}{" "}
              · {r.evidence_policy.replaceAll("_", " ")}
            </p>
            <p>
              {r.reason} · actor {r.created_by_id} · {r.created_at}
            </p>
            <details>
              <summary>
                Inspect rule definitions and specification provenance
              </summary>
              <ul>
                {r.rules.map((rule) => (
                  <li key={rule.id}>
                    <strong>{rule.name}</strong> · {rule.type} ·{" "}
                    {rule.attribute} · {rule.limit} {rule.unit} · margin{" "}
                    {rule.margin ?? "not applicable"} ·{" "}
                    {rule.enabled ? rule.severity : "disabled"}
                    <p>{rule.explanation}</p>
                    <p>
                      {rule.source_reference || "Reference unknown"}{" "}
                      {rule.source && (
                        <>
                          {" "}
                          · {rule.source.kind} {rule.source.id}
                        </>
                      )}
                    </p>
                    {rule.source?.kind === "import" && (
                      <a
                        href={`/api/v1/organizations/${org}/imports/${rule.source.id}/file/`}
                      >
                        Download private specification source
                      </a>
                    )}
                    <p>
                      Rule ID {rule.id} · rule version {rule.version}
                    </p>
                  </li>
                ))}
              </ul>
            </details>
            {manager && profile.status !== "archived" && (
              <>
                <button onClick={() => setSeed(r)}>
                  Use version {r.number} as next draft
                </button>
                {r.equipment_revision_id === profile.revision_id && (
                  <MutationForm
                    label={`Activate rule-set ${r.number}`}
                    action={async (data) => {
                      await compatibility.activate(org, id, r.id, {
                        expected_equipment_version: profile.version,
                        reason: text(data, "reason"),
                      });
                      reload();
                    }}
                  >
                    <Field
                      label="Activation review reason"
                      name="reason"
                      minLength={10}
                      required
                    />
                  </MutationForm>
                )}
              </>
            )}
          </article>
        ))}
        {rules && (
          <Pagination
            page={rulePage}
            count={rules.count}
            hasNext={!!rules.next}
            change={setRulePage}
          />
        )}
      </section>
      {manager && profile.status !== "archived" && (
        <RuleEditor
          key={`${seed?.id ?? "new"}-${profile.version}-${profile.latest_rule_version ?? 0}`}
          org={org}
          profile={profile}
          seed={seed}
          saved={() => {
            setSeed(null);
            setRulePage(1);
            reload();
          }}
        />
      )}
      <section className="catalog-panel">
        <h2>Equipment specification history</h2>
        {revisions?.results.map((r) => (
          <details key={r.id}>
            <summary>
              Specification {r.number} · {r.created_at} · actor{" "}
              {r.created_by_id}
            </summary>
            <p>{r.reason}</p>
            <pre className="snapshot-json">
              {JSON.stringify(r.definition, null, 2)}
            </pre>
          </details>
        ))}
        {revisions && (
          <Pagination
            page={revisionPage}
            count={revisions.count}
            hasNext={!!revisions.next}
            change={setRevisionPage}
          />
        )}
      </section>
      <p>
        These documented constraints do not certify gripping, dynamic stability,
        collision avoidance, regulatory compliance or robot safety.
      </p>
    </>
  );
}

function freshRule(attribute = "length"): Rule {
  return {
    id: crypto.randomUUID(),
    type: "maximum",
    name: `Maximum ${attribute}`,
    explanation:
      "Compare the recorded interval with the documented equipment limit.",
    severity: "hard",
    enabled: true,
    attribute,
    limit: "",
    unit: "",
    margin: "0",
    source_reference: "",
    source: null,
  };
}
export function rulePayload(rule: Rule) {
  const base = {
    id: rule.id,
    type: rule.type,
    name: rule.name,
    explanation: rule.explanation,
    severity: rule.severity,
    enabled: rule.enabled,
    source_reference: rule.source_reference,
    source: rule.source ? { kind: rule.source.kind, id: rule.source.id } : null,
  };
  return {
    ...base,
    ...(["maximum", "minimum"].includes(rule.type)
      ? {
          attribute: rule.attribute,
          limit: rule.limit,
          unit: rule.unit,
          margin: rule.margin || "0",
        }
      : rule.type === "required_attribute"
        ? { attribute: rule.attribute }
        : { allowed: rule.allowed ?? [] }),
  };
}
function RuleEditor({
  org,
  profile,
  seed,
  saved,
}: {
  org: string;
  profile: Equipment;
  seed: RuleSet | null;
  saved: () => void;
}) {
  const [rules, setRules] = useState<Rule[]>(
    () =>
      seed?.rules.map((r) => ({ ...r })) ??
      ["length", "width", "height", "mass"].map(freshRule),
  );
  const edit = (id: string, update: Partial<Rule>) =>
    setRules((rows) =>
      rows.map((r) => (r.id === id ? { ...r, ...update } : r)),
    );
  return (
    <section className="catalog-panel">
      <h2>Create a new immutable rule-set draft</h2>
      <p>
        Limits and units must come from documented specifications. A maximum
        margin reduces available capacity; a minimum margin increases the
        requirement. No unit or limit is guessed.
      </p>
      <MutationForm
        label="Save rule-set draft"
        action={async (data) => {
          await compatibility.createRules(org, profile.id, {
            expected_equipment_version: profile.version,
            expected_rule_version: profile.latest_rule_version ?? 0,
            name: text(data, "name"),
            reason: text(data, "reason"),
            evidence_policy: text(data, "evidence_policy"),
            rules: rules.map(rulePayload),
          });
          saved();
        }}
      >
        <Field
          label="Rule-set name"
          name="name"
          defaultValue={seed?.name}
          maxLength={160}
          required
        />
        <label className="field">
          Input evidence policy
          <select
            name="evidence_policy"
            defaultValue={seed?.evidence_policy ?? "measured_only"}
          >
            <option value="measured_only">
              Physically attested measurements only
            </option>
            <option value="reported_or_measured">
              Reported or physically attested; estimates never sufficient
            </option>
          </select>
        </label>
        {rules.map((rule, i) => (
          <fieldset className="rule-editor" key={rule.id}>
            <legend>
              Rule {i + 1} · {rule.name}
            </legend>
            <Field
              label="Rule name"
              value={rule.name}
              onChange={(e) => edit(rule.id, { name: e.target.value })}
              maxLength={160}
              required
            />
            <label className="field">
              Rule type
              <select
                value={rule.type}
                onChange={(e) =>
                  edit(rule.id, {
                    type: e.target.value as Rule["type"],
                    allowed: [],
                  })
                }
              >
                {[
                  "maximum",
                  "minimum",
                  "required_attribute",
                  "packaging_level",
                  "orientation",
                ].map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            {["maximum", "minimum", "required_attribute"].includes(
              rule.type,
            ) && (
              <label className="field">
                Attribute
                <select
                  value={rule.attribute}
                  onChange={(e) => edit(rule.id, { attribute: e.target.value })}
                >
                  {["length", "width", "height", "mass"].map((a) => (
                    <option key={a}>{a}</option>
                  ))}
                </select>
              </label>
            )}
            {["maximum", "minimum"].includes(rule.type) && (
              <div className="form-grid">
                <Field
                  label="Documented limit"
                  value={rule.limit ?? ""}
                  onChange={(e) => edit(rule.id, { limit: e.target.value })}
                  inputMode="decimal"
                  required
                />
                <label className="field">
                  Explicit rule unit
                  <select
                    value={rule.unit ?? ""}
                    onChange={(e) => edit(rule.id, { unit: e.target.value })}
                    required
                  >
                    <option value="">Choose unit</option>
                    {(rule.attribute === "mass"
                      ? ["g", "kg"]
                      : ["mm", "cm", "m"]
                    ).map((u) => (
                      <option key={u}>{u}</option>
                    ))}
                  </select>
                </label>
                <Field
                  label="Clearance margin (same unit)"
                  value={rule.margin ?? "0"}
                  onChange={(e) => edit(rule.id, { margin: e.target.value })}
                  inputMode="decimal"
                  required
                />
              </div>
            )}
            {["orientation", "packaging_level"].includes(rule.type) && (
              <fieldset>
                <legend>Allowed configurations</legend>
                {(rule.type === "orientation"
                  ? ["as_recorded", "swap_length_width"]
                  : levels
                ).map((v) => (
                  <label key={v}>
                    <input
                      type="checkbox"
                      checked={rule.allowed?.includes(v) ?? false}
                      onChange={(e) =>
                        edit(rule.id, {
                          allowed: e.target.checked
                            ? [...(rule.allowed ?? []), v]
                            : (rule.allowed ?? []).filter((x) => x !== v),
                        })
                      }
                    />
                    {v.replaceAll("_", " ")}
                  </label>
                ))}
              </fieldset>
            )}
            <Field
              label="Rule explanation"
              value={rule.explanation}
              onChange={(e) => edit(rule.id, { explanation: e.target.value })}
              minLength={5}
              maxLength={1000}
              required
            />
            <label className="field">
              Classification
              <select
                value={rule.severity}
                onChange={(e) =>
                  edit(rule.id, {
                    severity: e.target.value as Rule["severity"],
                  })
                }
              >
                <option value="hard">Hard constraint</option>
                <option value="advisory">
                  Advisory (does not determine compatibility)
                </option>
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={rule.enabled}
                onChange={(e) => edit(rule.id, { enabled: e.target.checked })}
              />
              Enabled
            </label>
            <Field
              label="Specification provenance reference"
              value={rule.source_reference}
              onChange={(e) =>
                edit(rule.id, { source_reference: e.target.value })
              }
              maxLength={1000}
            />
            <label className="field">
              Existing private source kind (optional)
              <select
                value={rule.source?.kind ?? ""}
                onChange={(e) =>
                  edit(rule.id, {
                    source: e.target.value
                      ? {
                          kind: e.target.value as "import" | "evidence",
                          id: rule.source?.id ?? "",
                        }
                      : null,
                  })
                }
              >
                <option value="">Reference text only</option>
                <option value="import">Organization import upload</option>
                <option value="evidence">
                  Product evidence in this organization
                </option>
              </select>
            </label>
            {rule.source && (
              <Field
                label="Existing source UUID"
                value={rule.source.id}
                onChange={(e) =>
                  edit(rule.id, {
                    source: { ...rule.source!, id: e.target.value },
                  })
                }
                required
              />
            )}
            <button
              type="button"
              onClick={() =>
                setRules((rows) => rows.filter((r) => r.id !== rule.id))
              }
            >
              Remove rule {i + 1}
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          disabled={rules.length >= 30}
          onClick={() => setRules((rows) => [...rows, freshRule()])}
        >
          Add rule
        </button>
        <Field
          label="Rule-set change reason"
          name="reason"
          minLength={5}
          maxLength={1000}
          required
        />
      </MutationForm>
    </section>
  );
}
