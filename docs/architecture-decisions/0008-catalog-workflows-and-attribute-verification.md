# ADR 0008 — Catalog workflows and attribute verification

Status: accepted for completion of Phase 3, 2026-10-14. Extends ADR 0007; its API-only/UI/verification deferrals are superseded here. No Phase 4 work is included.

## Product editing and packaging identities

Product PATCH requires `expected_revision` and a change reason. It copies the prior complete snapshot, applies validated descriptive changes, and appends an immutable revision; prior source links and bundled packaging snapshots remain unchanged. Concurrent stale edits return 409. SKU and organization ownership remain immutable through the API. Catalog names, descriptions and authors are read from revisions rather than duplicated on Product. Product lifecycle actor/time remain in audit history; `modified_by_id` represents the latest catalog revision's author.

The original revision-owned PackagingProfile table is retained as immutable historical snapshot data. New PackagingConfiguration identities support multiple independently named configurations at the same level, editable descriptors, optional units-per-package counts, lifecycle state, actor/time and optimistic versions. ConfigurationRevision preserves each accepted descriptor/lifecycle state and its reason. No old packaging snapshots are deleted, reinterpreted, or automatically merged into live configurations. Their existing revision APIs remain available. Current editable packaging uses the product-level `/packaging/` API; old bundled snapshots use `/revisions/{id}/packaging/`.

Packaging names are unique within a product, not globally. Owning organization is derived through Product. Independent configurations need not form a hierarchy; the original bundled snapshot API retains its reviewed hierarchy rules. New profile dimensions/mass are evidence-backed claims, rather than duplicate mutable numeric columns.

## Claims, verification and conflicts

AttributeClaim is an immutable typed assertion about a product or one of its live packaging configurations. Numeric attributes are length, width, height and mass, with the existing exact Decimal/unit/bounds validation. Text claims are restricted to name, brand, manufacturer, category and material; numbers/units cannot be supplied to a text claim. Unknown values are represented by the absence of a claim. A fixed nine-attribute state response exposes unknowns explicitly. Resource claim histories are bounded at 500 claims; writes beyond that limit require an operational review, never silent truncation/deletion.

Ordinary claim creation accepts reported or estimated only. Estimated claims require methodology and limitations. AI-source references can support estimated claims only; no model is executed. No generic confidence scalar is accepted because scores from different methods are not comparable. Claims can link an existing same-product source or atomically create validated provenance metadata with the claim.

Owner/admin physical verification requires a numeric observation, declared units/time, a physical_test source, instrument, procedure and limitations/sampling notes. It creates a new measured claim plus an immutable ClaimVerification recording the original claim, measured claim, authorized actor and server time. The original reported/estimated claim retains its basis and value. This is a recorded physical-measurement attestation, not independent proof of real-world truth, artifact integrity, certification or robot safety. Contributor-declared `method=measured` in the older snapshot API is explicitly an unverified report; it does not create this attestation.

ClaimSelection is a separate owner/admin decision with a rationale and timestamp. Selection cannot promote a claim's basis. Different canonical values or bounds/text remain conflicting claims. Only an explicit selection supplies a canonical attribute value. New contradictory claims after a selection invalidate the current canonical selection until another review; all selection records and competing claims persist. Textual catalog metadata remains editorial and is not silently overwritten by claim selection.

## Tenant and database boundaries

Reuse Phase 2 membership services, role checks, organization locks and scoped queries. Product and packaging writes lock the authorized organization before their resource and recheck current membership. Packaging mutations require the expected version. All source/claim/profile identifiers are resolved within the authorized product and exact attribute scope. Staff has no API bypass. Members can contribute and read product-scoped history; global organization audit remains owner/admin-only. Product or packaging archival retains history and blocks new claims/verification/selection/edits; owner/admin may reactivate.

PostgreSQL migration 0003 adds reversible, deferred constraint triggers for same-product revision/source and measurement/source links, same-revision ordered containment, claim source/profile ownership, and physical-verification claim/scope consistency. A measured claim must have its supporting verification record by transaction commit. Deferral permits creating the measured claim and verification atomically without circular insert ordering. SQLite does not install these PostgreSQL guards and cannot prove their behavior. These guards supplement, and do not replace, request authorization; they are not RLS or DB-level history immutability. DB operators remain trusted.

Existing append-only audit events continue to record fixed actions, actor, organization, target and time. Source text, customer descriptions and physical values stay in domain/history records, not event metadata. No competing audit system is introduced. Product/history/claim records have no ordinary delete endpoint; protected foreign keys and ORM guards preserve references. User deletion may null historical authorship while preserving records.

Migration 0004 adds finite decimal bounds matching the columns' representable integer ranges. PostgreSQL numeric NaN compares above finite numbers, so positivity alone does not exclude it. These constraints supplement API/ORM validation and reject raw-SQL NaN without inventing physical safety thresholds.

## Frontend and release scope

The existing Next.js session/CSRF transport serves the catalog, search/pagination, product creation/detail/edit, packaging editing/lifecycle, scoped claims, verification/selection and history screens. Role-dependent controls assist users; backend authorization remains mandatory. Unknown, reported, estimated, physically verified and conflicting states are visibly distinct. No authentication secrets are persisted in browser storage.

Evidence files, URL fetching, checksum verification, extraction, compatibility engines, billing, constraints, assessments and exports remain deferred. Source attribution/license declarations are unverified metadata. Production ingress/TLS, abuse limits, retention policy and Docker/hosted CI acceptance remain release gates where unexecuted.
