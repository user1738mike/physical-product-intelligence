# ADR 0007 — Product revisions and reference evidence

Status: accepted for Phase 3, 2026-10-14.

Completion note: ADR 0008 extends this initial API foundation with editable catalog workflows, stable packaging identities, attribute claims, authorized physical attestation, conflict selection and a frontend. Existing immutable snapshots and migration history remain compatible.

## Context

The first business domain must preserve product observations and provenance without undermining Phase 2 tenant authorization. Assessments will later require reproducible inputs. No private file storage, evidence parser or reviewed handling thresholds are available yet.

## Decision

Store product identity as an organization-owned UUID and immutable, tenant-unique, case-sensitive SKU. Create revision 1 with the product in one transaction. Changes append complete numbered snapshots rather than mutating history or implicitly merging with prior snapshots. Product archival/reactivation is a separate owner/admin operation. Members, admins and owners may read and contribute product revisions/evidence; new analyst/engineer roles require a later authorization decision.

Packaging profiles belong to one revision. Optional profiles use unit/inner/case/pallet levels; a unit root has quantity 1 and no containment. Containers refer to a present strictly smaller level and a positive quantity. Observations belong to a profile and preserve original values/units plus exact normalized decimals, optional enclosing bounds, method/time and evidence references. Metric-v1 accepts mm/cm/m → mm and g/kg → kg. Observations are not automatically selected, merged or interpreted as safety results. Missing values remain absent; unknown handling traits are null.

Evidence is product-owned immutable metadata, with a source reference/type, observation/recording times, author, attribution/license declarations and an optional declared SHA-256. It is explicitly `reference_only`; artifacts and digests are not fetched or verified. A new evidence record can correct a source, and a new product revision can reference it while retaining old history. This is a provenance foundation, not captured reproducible evidence for an assessment.

Tenant identity is stored on Product and derived through protected foreign keys. Transactional services enforce that revision/measurement evidence belongs to that same product, even within a tenant. Every request resolves current organization membership; nested identifiers never substitute for scope. Writes lock the organization before the product, serializing with membership/role changes and revision allocation. Unique product/revision constraints backstop duplicate SKUs/numbers. Success audit events share the transaction and include IDs/actions only.

Do not expose historical PATCH/DELETE, bulk ingestion or raw file/object keys. Read-only admin and ORM guards supplement the API. They are not DB-level immutability; trusted SQL operators can bypass them. Cross-table same-product and hierarchy checks live in services, with adversarial tests. DB constraints enforce compatible measurement dimensions, positive/enclosing values, valid levels and uniqueness where feasible.

## Consequences

Product provenance is reviewable and historical input references remain stable. Simple full snapshots avoid hidden merge rules but clients must resubmit retained fields, packaging and sources. Organization-level serialization is conservative and may limit write throughput; measure before narrowing locks. Tenant isolation requires disciplined service use; RLS and cross-table triggers are deferred.

No assessment, verified checksum, file immutability, license verification, consent validation, data retention policy or production release readiness is implied. Artifact capture/private storage/quarantine, sampling/observation selection, configurable constraints, assessments, product UI and retention-aware deletion remain subsequent work.
