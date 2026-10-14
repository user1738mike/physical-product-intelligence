"use client";

import { useState } from "react";
import {
  attributes,
  claimLabel,
  claimValue,
  numericAttributes,
  products,
  type Attribute,
  type AttributeState,
  type Claim,
  type SourceInput,
  type SourceType,
} from "../../lib/products";
import { Field, MutationForm, observedTime, text, TextField } from "./ui";

export function SourceFields({
  physical = false,
  sourceType,
  changeType,
}: {
  physical?: boolean;
  sourceType?: SourceType;
  changeType?: (value: SourceType) => void;
}) {
  return (
    <section className="source-fields">
      <h3>
        {physical
          ? "Supporting physical measurement record"
          : "Source and provenance"}
      </h3>
      <p className="quiet">
        Record a document or observation reference. File bytes and checksums are
        not captured or verified here.
      </p>
      {!physical && (
        <label className="field">
          <span>Source type</span>
          <select
            name="source_type"
            value={sourceType}
            onChange={(event) => changeType?.(event.target.value as SourceType)}
          >
            <option value="manual">User-entered information</option>
            <option value="supplier_document">Supplier documentation</option>
            <option value="manufacturer_spec">
              Manufacturer specification
            </option>
            <option value="imported_catalog">Imported catalog reference</option>
            <option value="ai_estimate">AI / external model estimate</option>
            <option value="physical_test">
              Physical test reference (unverified until attested)
            </option>
            <option value="other">Other reference</option>
          </select>
        </label>
      )}
      <div className="form-grid">
        <Field
          label="Source title"
          name="source_title"
          required
          maxLength={200}
        />
        <Field
          label="Source or notebook reference"
          name="source_reference"
          required
          maxLength={2000}
        />
        <Field
          label="Observer / attribution"
          name="attribution"
          required
          maxLength={200}
        />
        <Field
          label="License or rights declaration (state unknown if unconfirmed)"
          name="license"
          required
          maxLength={200}
        />
        <Field
          label="Observed at (your local time)"
          name="observed_at"
          type="datetime-local"
          required
        />
      </div>
      <TextField
        label="Source notes (optional)"
        name="source_description"
        maxLength={4000}
      />
    </section>
  );
}
function source(data: FormData, source_type: SourceType): SourceInput {
  return {
    title: text(data, "source_title"),
    source_type,
    source_reference: text(data, "source_reference"),
    attribution: text(data, "attribution"),
    license: text(data, "license"),
    observed_at: observedTime(data),
    description: text(data, "source_description"),
  };
}

export function NumericFields({
  attribute,
  initial,
}: {
  attribute: string;
  initial?: Claim;
}) {
  return (
    <>
      <div className="form-grid">
        <Field
          label="Value"
          name="value"
          inputMode="decimal"
          required
          maxLength={24}
          defaultValue={initial?.value ?? ""}
        />
        <label className="field">
          <span>Declared unit</span>
          <select
            name="unit"
            required
            key={attribute}
            defaultValue={initial?.unit || ""}
          >
            <option value="">Choose an explicit unit</option>
            {(attribute === "mass" ? ["g", "kg"] : ["mm", "cm", "m"]).map(
              (unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ),
            )}
          </select>
        </label>
        <Field
          label="Uncertainty lower bound (optional)"
          name="lower"
          inputMode="decimal"
          maxLength={24}
        />
        <Field
          label="Uncertainty upper bound (optional)"
          name="upper"
          inputMode="decimal"
          maxLength={24}
        />
      </div>
      <p className="quiet">
        Positive decimal values only, up to six decimal places. Supply both
        bounds or neither; bounds must enclose the value. Unknown measurements
        should be left unrecorded.
      </p>
    </>
  );
}

export function ClaimForm({
  org,
  product,
  packaging,
  saved,
}: {
  org: string;
  product: string;
  packaging?: string;
  saved: () => void;
}) {
  const [attribute, setAttribute] = useState<Attribute>("mass");
  const [basis, setBasis] = useState<"reported" | "estimated">("reported");
  const [sourceType, setSourceType] = useState<SourceType>("manual");
  const [nonce, setNonce] = useState(0);
  return (
    <MutationForm
      key={nonce}
      label="Record attribute claim"
      action={async (data) => {
        const numeric = numericAttributes.includes(attribute);
        await products.addClaim(
          org,
          product,
          {
            attribute,
            basis,
            value: numeric ? text(data, "value") : null,
            unit: numeric ? text(data, "unit") : "",
            text_value: numeric ? "" : text(data, "text_value"),
            lower: numeric ? text(data, "lower") || null : null,
            upper: numeric ? text(data, "upper") || null : null,
            method: text(data, "method"),
            limitations: text(data, "limitations"),
            observed_at: observedTime(data),
            source: source(data, sourceType),
          },
          packaging,
        );
        setNonce(nonce + 1);
        setAttribute("mass");
        setBasis("reported");
        setSourceType("manual");
        saved();
      }}
    >
      <div className="form-grid">
        <label className="field">
          <span>Attribute</span>
          <select
            name="attribute"
            value={attribute}
            onChange={(event) => setAttribute(event.target.value as Attribute)}
          >
            {attributes.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Claim basis</span>
          <select
            name="basis"
            value={basis}
            onChange={(event) =>
              setBasis(event.target.value as "reported" | "estimated")
            }
          >
            <option value="reported">Reported — not physically verified</option>
            <option value="estimated">
              Estimated — not physically verified
            </option>
          </select>
        </label>
      </div>
      {numericAttributes.includes(attribute) ? (
        <NumericFields attribute={attribute} />
      ) : (
        <Field
          label="Reported text value"
          name="text_value"
          required
          maxLength={2000}
        />
      )}
      <TextField
        label={
          basis === "estimated"
            ? "Estimation method / model and version (required)"
            : "Observation or transcription method (optional)"
        }
        name="method"
        required={basis === "estimated"}
      />
      <TextField
        label={
          basis === "estimated"
            ? "Estimate limitations (required)"
            : "Limitations (optional)"
        }
        name="limitations"
        required={basis === "estimated"}
      />
      <SourceFields
        sourceType={sourceType}
        changeType={(value) => {
          setSourceType(value);
          if (value === "ai_estimate") setBasis("estimated");
        }}
      />
      <p className="notice">
        Manual entry does not verify a physical value. Estimates remain
        estimates; no AI pipeline runs in this phase.
      </p>
    </MutationForm>
  );
}

export function VerificationForm({
  org,
  product,
  claim,
  packaging,
  saved,
}: {
  org: string;
  product: string;
  claim: Claim;
  packaging?: string;
  saved: () => void;
}) {
  return (
    <MutationForm
      label="Record physical verification"
      action={async (data) => {
        await products.verify(
          org,
          product,
          claim.id,
          {
            value: text(data, "value"),
            unit: text(data, "unit"),
            lower: text(data, "lower") || null,
            upper: text(data, "upper") || null,
            observed_at: observedTime(data),
            instrument: text(data, "instrument"),
            procedure: text(data, "procedure"),
            notes: text(data, "notes"),
            source: source(data, "physical_test"),
          },
          packaging,
        );
        saved();
      }}
    >
      <p className="notice">
        This records your authorized attestation of a physical measurement. It
        creates a separate measured claim and preserves the original claim. It
        does not verify file bytes or certify handling safety.
      </p>
      <NumericFields attribute={claim.attribute} />
      <Field
        label="Measurement instrument / equipment reference"
        name="instrument"
        required
        maxLength={200}
      />
      <TextField
        label="Physical measurement procedure"
        name="procedure"
        required
        minLength={10}
      />
      <TextField
        label="Measurement limitations and sampling notes"
        name="notes"
        required
        minLength={10}
      />
      <SourceFields physical />
      <label className="checkbox">
        <input type="checkbox" name="attestation" required /> I attest that this
        record describes an actual physical measurement and its limitations.
      </label>
    </MutationForm>
  );
}

export function ClaimCard({
  claim,
  org,
  product,
  packaging,
  privileged,
  writable,
  saved,
}: {
  claim: Claim;
  org: string;
  product: string;
  packaging?: string;
  privileged: boolean;
  writable: boolean;
  saved: () => void;
}) {
  return (
    <article className="claim-card">
      <div className="claim-heading">
        <h3>
          {claim.attribute}: {claimValue(claim)}
        </h3>
        <span className={`badge ${claim.basis}`}>{claimLabel(claim)}</span>
      </div>
      {claim.value !== null && (
        <p>
          Normalized observation:{" "}
          <strong>
            {claim.canonical_value} {claim.canonical_unit}
          </strong>
          {claim.canonical_lower !== null && (
            <>
              {" "}
              · bounds {claim.canonical_lower}–{claim.canonical_upper}{" "}
              {claim.canonical_unit}
            </>
          )}
        </p>
      )}
      <dl className="provenance">
        <div>
          <dt>Source</dt>
          <dd>
            {claim.evidence.title} · {claim.evidence.source_type}
          </dd>
        </div>
        <div>
          <dt>Reference</dt>
          <dd>{claim.evidence.source_reference}</dd>
          {claim.evidence.source_artifact && (
            <>
              <dt>Captured source</dt>
              <dd>
                <a href={claim.evidence.source_artifact.download_path}>
                  Download private source ·{" "}
                  {claim.evidence.source_artifact.location}
                </a>
                <br />
                Computed SHA-256: {claim.evidence.source_artifact.sha256}
              </dd>
            </>
          )}
        </div>
        <div>
          <dt>Attribution</dt>
          <dd>{claim.evidence.attribution}</dd>
        </div>
        <div>
          <dt>Rights declaration</dt>
          <dd>{claim.evidence.license}</dd>
        </div>
        <div>
          <dt>Observed</dt>
          <dd>{new Date(claim.observed_at).toLocaleString()}</dd>
        </div>
        <div>
          <dt>Recorded</dt>
          <dd>
            {new Date(claim.recorded_at).toLocaleString()} · actor{" "}
            {claim.recorded_by_id ?? "removed"}
          </dd>
        </div>
      </dl>
      {claim.method && (
        <p>
          <strong>Method:</strong> {claim.method}
        </p>
      )}
      {claim.limitations && (
        <p>
          <strong>Limitations:</strong> {claim.limitations}
        </p>
      )}
      {claim.verification_record && (
        <section className="verified-note">
          <h4>Physical measurement attestation</h4>
          <p>
            Actor {claim.verification_record.verified_by_id ?? "removed"} ·{" "}
            {new Date(claim.verification_record.verified_at).toLocaleString()}
          </p>
          <p>Instrument: {claim.verification_record.instrument}</p>
          <p>{claim.verification_record.procedure}</p>
          <p>{claim.verification_record.notes}</p>
        </section>
      )}
      {claim.verifications.length > 0 && (
        <p className="quiet">
          {claim.verifications.length} separate physical measurement record(s)
          reference this original claim. Its original basis remains unchanged.
        </p>
      )}
      {privileged && writable && (
        <div className="claim-actions">
          {claim.basis !== "measured" &&
            numericAttributes.includes(claim.attribute) && (
              <details>
                <summary>Record a physical measurement</summary>
                <VerificationForm
                  org={org}
                  product={product}
                  claim={claim}
                  packaging={packaging}
                  saved={saved}
                />
              </details>
            )}
          <details>
            <summary>Select this claim for the attribute</summary>
            <MutationForm
              label="Select claim with rationale"
              action={async (data) => {
                await products.select(
                  org,
                  product,
                  claim.attribute,
                  claim.id,
                  text(data, "rationale"),
                  packaging,
                );
                saved();
              }}
            >
              <TextField
                label="Selection rationale and conflict considerations"
                name="rationale"
                required
                minLength={10}
              />
              <p className="quiet">
                Selection does not change the source basis. A new conflicting
                claim requires another review.
              </p>
            </MutationForm>
          </details>
        </div>
      )}
    </article>
  );
}

export function AttributeSummary({ states }: { states: AttributeState[] }) {
  return (
    <section className="panel table-wrap" aria-label="Attribute data quality">
      <h3>Attribute data quality</h3>
      <p className="quiet">
        Only an explicitly selected claim supplies a canonical attribute value.
        Selection never promotes an estimate to verified.
      </p>
      <table>
        <thead>
          <tr>
            <th scope="col">Attribute</th>
            <th scope="col">State</th>
            <th scope="col">Claims</th>
            <th scope="col">Selected value</th>
          </tr>
        </thead>
        <tbody>
          {states.map((state) => (
            <tr key={state.attribute}>
              <th scope="row">{state.attribute}</th>
              <td>
                <span className={`badge ${state.status}`}>
                  {state.status === "verified"
                    ? "Physically verified (attested)"
                    : state.status}
                </span>
                {state.conflicting && (
                  <small>
                    {state.selected_claim
                      ? "Competing claims preserved"
                      : "Unresolved disagreement"}
                  </small>
                )}
              </td>
              <td>{state.claim_count}</td>
              <td>
                {state.selected_claim ? (
                  <>
                    {claimValue(state.selected_claim)}
                    <small>{claimLabel(state.selected_claim)}</small>
                    <small>Rationale: {state.selection?.rationale}</small>
                  </>
                ) : state.claim_count ? (
                  "No canonical value selected"
                ) : (
                  "Unknown"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
