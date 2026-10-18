# Customer integrations API, schema 1

This increment provides organization-bound read credentials, frozen assessment exports and `assessment.completed` notifications. API traffic, exports and notification retries are operational usage; they do not create charges. Payment ingestion is a separate billing trust boundary.

## Authentication and permissions

Send `Authorization: Bearer <credential>` to `/api/v1/integration/`. Never put a bearer value in a URL, query, example source, log or command argument. Cookies do not authenticate these routes. A credential has a public UUID lookup identifier and a random 256-bit secret; only its SHA-256 verifier is stored. Creation and rotation reveal the complete value once, in an authorized no-store response. Metadata never includes the verifier or secret. The UI holds a reveal only in component memory and clears it on dismissal, refresh/focus or organization change; it uses no persistent browser storage.

| Caller | Allowed operations |
| --- | --- |
| Active organization owner/admin, session + CSRF | Inspect management metadata; create/rotate credentials and configure/rotate destinations when current entitlements permit; revoke credentials, disable destinations, inspect restricted delivery history; explicitly replay an eligible delivery. |
| Member | No integration management, including direct API requests. |
| Scoped credential | Only the matching integration GET/HEAD routes below. No session management, billing, evidence file downloads, upload, assessment creation, catalog mutation or administrative API. |
| Staff | No tenant HTTP bypass. Separate protected database-owner operator commands can publish a reviewed plan or dispatch a bounded batch. |

Every credential request checks expiry/revocation, the issuing user's active owner/admin membership, active organization and the Phase 9A plan extension. Removal, downgrade or user deactivation invalidates subsequent requests in every process. No positive authentication cache is used. A caller cannot select another organization by URL/header/body; guessed foreign resource IDs return 404. Invalid credentials return 401, scope/role/entitlement denial 403. Scope checks precede resource queries. An admitted request already in flight cannot be recalled; subsequent admissions recheck authorization.

Rotation creates a new identity and verifier and revokes the previous credential immediately by default. Explicit `revoke_old:false` permits overlap only until the old credential's existing expiry, within the same finite allowance. Compromise requires immediate revocation. New expiry must be between one minute and 90 days. Expired/revoked records remain metadata for audit.

## Management routes

All paths below are relative to `/api/v1/organizations/{organization_id}/integrations/`, require the existing session/CSRF mechanism, and scope the resource before resolving it.

| Method/path | Contract |
| --- | --- |
| GET empty path | `credential_creation_available`, `outbound_available`, finite `allowances`, credential/destination metadata and at most 100 recent deliveries. At most 100 credential/destination records, with active credentials/enabled destinations first. No general secret retrieval. |
| POST `credentials/` | Strict `{name, scopes, expires_at, rotate?: credential_uuid, revoke_old?: boolean}`. Returns metadata plus `secret` once, HTTP 201. |
| POST `credentials/{id}/revoke/` | Idempotent final revocation, including when new work is unavailable. |
| POST `destinations/` | Strict `{url, subscriptions, enabled}`; creation requires `enabled:true`. Returns metadata and signing `secret` once, HTTP 201. Only `assessment.completed` or an empty subscription list is supported. |
| PATCH `destinations/{id}/` | `{url, subscriptions, enabled, expected_revision}`. Changes advance the revision and pause previous queued/claimed deliveries. Disabling remains available after commercial expiry. |
| POST `destinations/{id}/rotate/` | `{immediate:false}` gives a maximum 24-hour previous-key overlap. `immediate:true` drops the old signing key immediately. New signing secret is revealed once. |
| POST `deliveries/{id}/replay/` | Explicit audited replay of the same immutable event/body to its same unchanged enabled destination revision. At most three replays. A claimed delivery cannot be replayed. No assessment or usage is recreated. |

Metadata/history and credential revocation remain accessible to authorized session owners/admins when new commercial work is unavailable. Disabled destination URLs can be retired even if an operator has removed the host from the allowlist. An enabled destination cannot be re-enabled to bypass its allowance.

## Credential reads

| Scope | GET/HEAD route |
| --- | --- |
| `catalog:read` | `/api/v1/integration/products/`, `/products/{id}/` |
| `assessments:read` | `/api/v1/integration/assessments/`, `/assessments/{id}/` |
| `assessments:export` | `/api/v1/integration/assessments/{id}/export/json/` or `/export/csv/` |

Scopes are independent; export scope does not imply assessment listing. Wildcard/admin/billing/upload/write scopes are rejected. Catalog reads use the existing revision-aware catalog service; response fields are identity, SKU, current name, active state and revision number. Assessment list rows contain ID, creation time, outcome and product ID. Detail and JSON export use the same frozen projection described below. Product/assessment joins always begin with the credential's organization.

Lists accept strict `limit` (1–25, default 25), `after` (exclusive UUID), catalog-only bounded SKU `search`, and assessment-only `overall` (`compatible`, `incompatible`, `indeterminate`). Unknown/mismatched filters fail. Ordering is ascending immutable UUID; response is `{schema_version:"1", results:[...], next_after:uuid|null}`. Continue until `next_after:null`. Pagination is stable by identifier, not a snapshot across concurrent inserts; newly inserted lower UUIDs require a fresh traversal. No bulk export silently truncates records. Each export is one assessment. Resource queries have a three-second statement budget; each response is capped at 1 MiB, with explicit `export_limit` on overflow. Consumers should narrow lists and handle errors rather than assume partial data is complete.

Shared PostgreSQL admission allows 60 requests/minute per credential and 180/minute per organization, independent of client IP and untrusted headers. Rotation cannot reset the organization bucket. At most two active admissions per credential/four per organization; abandoned admissions expire after 20 seconds. HTTP 429 includes bounded `Retry-After`. Fixed windows may admit traffic on either side of a minute boundary; they are not a sliding-window or throughput guarantee.

Historical reads may continue under the last ended active assignment's integration policy, subject to a valid issuer membership and active organization. Suspension, policy removal or an active replacement without integration access denies credential use. Existing authorized session history APIs retain their Phase 9A behavior. New credentials/destinations and outbound dispatch always require a current active entitled assignment.

## Export schemas

JSON schema `1` includes `assessment_id`, `organization_id`, `assessed_at`, actual `overall`, `engine_version`, product/package/equipment revision identifiers, `rule_set_id`, frozen `inputs`, `equipment_snapshot`, `rule_snapshot`, `results`, `summary` and an explicit limitations notice. Rule snapshots retain their version number and frozen rules. Inputs/results retain normalized decimal strings and units, null/unknown values, missing/conflicting states, explanations and opaque evidence/provenance identifiers. No current catalog measurement is substituted. URL/file/storage/source-link fields and direct creator/modifier/measurement-verifier fields are omitted recursively; other opaque audit identifiers may remain as provenance references. Original document bytes, unrestricted file links, billing and credentials are excluded. Decimal strings are not converted through floating point; unknown never becomes zero.

CSV has one header and one row per assessment, fixed columns:

`schema_version,assessment_id,assessed_at,overall,engine_version,product_revision_id,packaging_revision_id,equipment_revision_id,rule_set_id,summary,inputs_json,equipment_snapshot_json,rule_snapshot_json,results_json`.

UTF-8, RFC-style CSV quoting and CRLF records are used. Nested snapshots are compact JSON text in their respective cells; null is the literal JSON `null`. Text beginning with formula markers `=`, `+`, `-`, `@` after leading whitespace, or beginning with tab/CR/LF, receives a leading apostrophe. This protective CSV representation may differ from source text; exact unmodified values remain in JSON. Downloads use private no-store responses and fixed UUID-derived filenames.

Neither format is a safety certificate or evidence of physical performance beyond the underlying deterministic assessment. Additive schema fields may appear; consumers must tolerate them. Changed meanings/types require a new schema version. Consumers must not reinterpret `indeterminate` as compatible.

## Versioned plan integration

Immutable `integrations.PlanPolicy` extends only a newly published, unassigned plan version >=2, with `api_enabled`, `webhooks_enabled`, `credentials_limit` (0–20), and `destinations_limit` (0–10). No existing plan/assignment is modified by migration. Plan/usage exposes `integration_api` and `outbound_webhooks`; management exposes finite allowances. Missing policy fails closed. No price is invented. Protected operator `publish_integration_plan` copies the reviewed base plan's existing features/limits into a higher version, adds the extension, and leaves assignment as a separate explicit commercial operator action.

See [delivery operations](webhook-delivery.md), [offline example client](../examples/warehouse_client.py), and [reference receiver](../examples/warehouse_receiver.py). Their defaults contact no external service.
