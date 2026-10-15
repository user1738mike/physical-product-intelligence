# Equipment and recorded-input compatibility

Phase 5 adds organization-owned equipment specifications, immutable rules and immutable assessments. These establish only whether recorded inputs satisfy documented static constraints. They do not certify physical operation, gripping, stability, collision avoidance, regulatory compliance or robot-cell safety.

## Equipment lifecycle

An equipment UUID and tenant-unique, case-sensitive immutable code identify a profile. Its definition records name, description, manufacturer/model when known, category, operational context, supported packaging levels, specification reference and orientation/handling notes. Blank specifications remain unknown. Numeric constraints live in versioned rules; notes are not executable constraints. Categories are conveyor, storage, tote_bin, shelving, picking_cell, gripper and handling. This release deliberately has no shared manufacturer/installation hierarchy.

Creation writes specification revision 1 in draft. Owner/admin edits require `expected_version` and a reason, append a full specification revision and return to draft. Activation of an eligible rule set sets the equipment active and increments its edit version. Archive/restore uses the state endpoint, appends a specification copy and preserves history. Restoring requires a new rule set bound to that specification before activation. No hard-delete endpoint exists.

Rule sets are immutable, numbered per equipment and bound to an exact specification revision. Editing means creating another set, optionally retaining rule UUIDs. Each rule has a stable UUID, set/version number, name, explanation, classification, enabled flag, source metadata and actor/timestamps. Activation is a separate immutable actor/time/reason record. It requires the current nonarchived specification, documented supported levels and operational context, at least one enabled hard rule, and a specification reference or authorized linked source for every enabled rule. Known `ai_estimate` evidence cannot authorize equipment activation. A source reference is an attribution, not proof that the manufacturer authenticated it.

Multiple activated versions of the current specification may be explicitly selected. There is no implicit latest-rule fallback. Editing equipment makes all older-specification sets ineligible for new assessments; old assessments remain readable. Immutable drafts can be inspected but never evaluated.

## Rules and deterministic semantics

| Type | Operands and behavior |
| --- | --- |
| maximum | length/width/height/mass, positive limit, explicit unit, nonnegative clearance; inclusive effective maximum = limit minus clearance |
| minimum | same operands; inclusive effective minimum = limit plus clearance |
| required_attribute | a numeric attribute with qualifying evidence |
| packaging_level | explicit allowed unit/inner/case/pallet levels |
| orientation | explicit allowed as_recorded/swap_length_width choices |

Hard failures decide the result. Advisory failures remain visible but do not prevent a compatible result. Disabled rules are not applicable and cannot supply required coverage. Unknown types, extra operands, expressions, invalid UUIDs, incompatible units, NaN/infinity, nonpositive values and excessive precision are rejected. No dynamic code or expressions execute.

Supported units are mm/cm/m normalized to mm and g/kg normalized to kg using existing `metric-v1` Decimal conversions. Original values, units, margins, canonical operands and inclusive effective bounds are retained. Maximum clearance must be smaller than its limit. Limits support twelve integer and six fractional digits. No binary floating-point comparisons occur.

An interval passes a maximum only when its upper bound is within the effective limit; it fails only when its lower bound exceeds it. A straddling interval is indeterminate. Minimum rules use the converse. Exact boundaries pass. Orientation must be explicitly supplied for dimensional evaluation; the only supported rotation swaps length and width, leaving height unchanged. Dimensions are never automatically sorted to obtain a favorable fit.

In addition to explicit rules, the engine checks documented equipment packaging scope. Packaging scope derives from the selected profile; product-level scope requires an explicit handling level. Unknown levels are indeterminate. **A compatible static-envelope result requires enabled hard maxima for all four attributes: length, width, height and mass.** Missing maxima generate individual indeterminate checks, never unlimited capacity. A partial set may be activated for useful failure/unknown results but cannot establish a complete envelope fit.

Evidence policy is explicit: `reported_or_measured` permits reported and attested measured numeric claims; `measured_only` requires measured claims linked to an existing verification. Estimates never qualify for a pass. Physical attestations retain their actual procedure/instrument/actor; no independent laboratory validation is implied. Existing editorial canonical selections do not erase conflicting claims. Any conflict prevents a pass; credible eligible intervals that all reliably violate a constraint can establish failure. Estimated disagreement remains visible. Evidence with missing/inconsistent normalized operands cannot pass.

Overall precedence: reliable applicable hard failure → `incompatible`; otherwise unresolved hard checks → `indeterminate`; otherwise all required hard checks and envelope coverage pass → `compatible`. An empty/no-op evaluation never passes. No separate review state is implemented.

## API and permissions

All paths below are relative to `/api/v1/organizations/{organization_id}/`. Authentication is the existing session cookie plus fresh `X-CSRFToken` for mutations. Organization IDs select scope but grant no authority. Current membership, active tenant and nested ownership are checked server-side; staff has no bypass. Owner/admin manages equipment/rules/activation; every active member can read and run assessments. Foreign objects return 404, role/session denials follow existing 403 behavior, stale versions/reused conflicting keys return 409, malformed requests return 400.

| Path | Methods |
| --- | --- |
| equipment/ | GET search/status/category/page; POST create |
| equipment/{id}/ | GET; PATCH definition with expected_version/reason |
| equipment/{id}/state/ | POST status draft or archived, expected_version, reason |
| equipment/{id}/revisions/ | GET immutable paginated history |
| equipment/{id}/rule-sets/ | GET history; POST new immutable version |
| equipment/{id}/rule-sets/{rule}/ | GET exact version |
| equipment/{id}/rule-sets/{rule}/activate/ | POST expected_equipment_version/reason |
| assessments/ | POST evaluation; GET filtered history |
| assessments/{id}/ | GET immutable snapshot |
| assessments/{id}/compare/?other_id={uuid} | GET stored-result differences |

Collections use existing 25-item pagination. Equipment search covers code/name. Assessment filters: product_id, equipment_id, overall, date_from/date_to (inclusive ISO datetimes) and page. History defers large snapshot fields and avoids per-row queries. Comparison requires the same product, package scope and equipment; differences are aligned by stable rule UUID, retaining full before/after results. It does not reevaluate history.

### Example sequence

Create equipment (`POST equipment/`):

```json
{"code":"CONVEYOR-TEST-1","name":"Synthetic conveyor fixture","category":"conveyor","operational_context":"Case handling, static fixture only","supported_levels":["case"],"source_reference":"Synthetic manual; not a real manufacturer specification"}
```

Create rules (`POST equipment/{id}/rule-sets/`). This deliberately partial example can only yield incompatible/indeterminate until all required maxima are documented:

```json
{"expected_equipment_version":1,"expected_rule_version":0,"name":"Fixture limits","reason":"Record documented fixture constraint","evidence_policy":"reported_or_measured","rules":[{"id":"7c17e1cb-a7f3-4ae4-ab9e-bbf6504322b5","type":"maximum","name":"Maximum length","explanation":"Static opening with documented clearance","severity":"hard","enabled":true,"attribute":"length","limit":"60","unit":"cm","margin":"1","source_reference":"Synthetic manual section 2","source":null}]}
```

Optional source is `{ "kind": "evidence" | "import", "id": "UUID" }`, checked against existing tenant evidence/imports and copied as metadata. No second evidence catalog is introduced. Imported documents retain private authenticated download access. Activation: `POST .../activate/` with `{"expected_equipment_version":1,"reason":"Reviewed synthetic fixture specifications"}`.

Run (`POST assessments/`), replacing UUID labels with actual API-returned UUIDs:

```json
{"request_id":"ef3985a0-26d2-4a08-8494-9dab948d2f7c","product_id":"PRODUCT_UUID","packaging_id":"PACKAGE_UUID","equipment_id":"EQUIPMENT_UUID","rule_set_id":"RULE_SET_UUID","orientation":"as_recorded","parent_id":null}
```

For product scope omit packaging_id and explicitly supply `product_level`, or leave it unknown and receive indeterminate. A package's level cannot be overridden. A missing length produces a stored result such as:

```json
{"overall":"indeterminate","results":[{"name":"Maximum length","status":"indeterminate","attribute":"length","reason":"No qualifying recorded input establishes this constraint."}]}
```

This is an abbreviated illustrative response, not a complete API object. Actual responses also preserve rule IDs/versions, evidence claims, originals, canonical units, margins/effective bounds, reasons, engine/schema versions, actor/time and exact record revisions. With a complete documented envelope, qualifying consistent inputs and explicit allowed level/orientation, all hard checks can pass. A reliable mass exceedance instead returns incompatible even if length is missing.

Use a new request UUID for every new evaluation. Same key plus same operands returns the original snapshot (currently HTTP 201 for both create/retry), even if catalog data changed. Same key plus different operands returns 409. Reassess with a new UUID and optional `parent_id` pointing to the same targets. Do not reuse a key to request updated results.

## Integrity and resource limits

The organization lock serializes membership/catalog/evaluation writes. Transactional services write snapshots plus audit events together. Snapshot models block supported ORM updates/deletes; ordinary APIs expose no assessment/rule mutation or deletion. PostgreSQL deferred scope triggers backstop reference integrity for rule specifications and assessment product/package/revision/equipment/rules/parent relations. These are not RLS or protection from trusted database operators rewriting JSON. Historical interpretation comes from frozen JSON, not current joins or current engine execution.

Limits: 30 rules/set, 100 numeric claims in the chosen assessment scope, existing 64 KiB normal request cap, and best-effort per-process assessment-collection throttle of 60/hour. Exceeding the claim bound rejects evaluation rather than silently dropping evidence. Production still needs shared ingress limits, private storage/scanner controls and privileged audit retention.

Engine `warehouse-fit-v1`, schema `warehouse-rules-v1`, conversion `metric-v1` identify implemented semantics. Source content authenticity, externally hosted references and claims' physical correctness remain outside the guarantee. Source bytes/links follow Phase 4 private retention policies; mutable links alone are not captured artifacts. This release does not infer structured values from legacy bundled observations or free-text notes, model shape/friction/center of gravity/dynamics, add imperial units, AI judgments, background infrastructure, installation hierarchies or safety certification.

## Run and verify

Use existing setup and environment instructions in README; no dependency or `.env` changes are required. Apply migrations without resetting data:

```powershell
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test accounts organizations operations products compatibility --settings=config.settings.test
docker compose exec -T backend python manage.py spectacular --validate --fail-on-warn --file /tmp/openapi.yaml
```

Frontend: `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run format:check`, `npm.cmd run build`. The disposable Phase 3 live smoke now includes Phase 4 imports and Phase 5 assessments through the production proxy. Never run data-creating smoke checks on customer data. See the [completion report](phase5-completion-report.md) for actual native/PostgreSQL results and the unresolved Compose host limitation.

## Phase 6 integration

Optional AI candidates can enter this engine only after validated human review/application through the existing catalog services. The evaluator itself is unchanged. New assessments freeze extraction provenance from approved source claims; older snapshots remain unchanged. AI cannot edit rules/activations or request an automatic reassessment. See [AI extraction guide](ai-extraction-api.md).
