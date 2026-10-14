# Domain model

Organization, Membership and AuditEvent are implemented in Phase 2; User remains Django's migration-safe global `auth.User`. Phase 3 implements Product, ProductRevision, PackagingProfile, Measurement, Evidence and immutable RevisionEvidence links. Constraints, assessments and integrations below remain planned. Tenant entities use UUIDs and UTC timestamps. Measurements use exact decimals; tenant ownership is derived through the product at every boundary.

| Entity | Relationships and invariants |
| --- | --- |
| Organization | Tenant boundary; lifecycle and retention policy |
| User / Membership | Global identity; membership joins user to organization with explicit role; unique pair |
| Product / ProductRevision | Implemented: tenant-unique case-sensitive immutable SKU, archival state; immutable numbered full revisions with name, brand, manufacturer, model, category, description, change reason and author |
| PackagingProfile | Implemented: immutable revision-owned unit/inner/case/pallet snapshots; optional smaller contained level and positive count; unit root count 1, no cycles, nullable fragile/stackable traits |
| Measurement | Implemented: packaging-owned mass/length/width/height observations; original/canonical decimal values and uncertainty bounds, method/time, required evidence, conversion version; competing observations retained |
| Evidence / RevisionEvidence | Implemented: product-owned immutable provenance metadata and immutable revision links; source reference/type, declared unverified SHA-256, attribution/license declarations, observation/recording times and author. Artifacts, quarantine and verified checksums deferred |
| ConstraintProfile / ConstraintVersion | Organization-owned profile with immutable rule versions and applicability to packaging level |
| Assessment / ConstraintOutcome | Organization, input revision snapshot, constraint version snapshot, evaluator version, output, provenance and reviewer |
| AuditEvent | Organization or system scope, actor, action, target, timestamp, request ID; append-only service interface |
| IntegrationCredential | Organization-scoped credential digest, scope, expiry and revocation; raw token shown once |

## Provenance and reproducibility
Measurements retain original and canonical representations. Phase 3 accepts mm/cm/m for length, width and height (canonical mm), and g/kg for mass (canonical kg), with exact decimal factors under `metric-v1`. Input values/bounds allow up to 12 integer and six fractional digits; canonical storage allows 15 integer and nine fractional digits. Invalid dimensions, nonfinite/nonpositive values, excess precision, partial bounds and bounds not enclosing the observation are rejected. Missing measurements and nullable traits mean unknown; no assessment or preferred observation is inferred. Conflicting observations remain separate. Sampling populations and a selection/rationale workflow remain deferred.

Each product revision is a complete snapshot; omissions are not inherited from its predecessor. Packaging may be empty when unknown; otherwise it requires a unit root. Every non-unit level references a present strictly smaller level and a contained count, so containment cannot cycle. Sources for measurements are automatically included in the revision's evidence links. Evidence must belong to the same product, including when the source and target products share a tenant. Source references and contributor-declared checksums/licenses do not prove artifact capture or rights verification. Authors may become null on user deletion; historical records and links persist.

Published assessments reference immutable revisions and serialize complete normalized input, rules, engine version, evidence hashes, unit conversion version, execution timestamp and decision policy. Use pass/fail/unknown/not-applicable outcomes with reasons and per-rule evidence links. Re-running changed rules creates a new assessment. Constraints with uncertain ranges require a documented conservative boundary policy. Mutable external URLs alone are insufficient evidence. Physical test results and model inference outputs need their own versioned methods and artifacts later.

## Integrity and deletion
All tenant-owned foreign key relationships must be checked for same-organization ownership inside transactions; a UUID does not grant access. Add database constraints where feasible, including tenant-specific revision uniqueness. Deletion uses retention-aware workflows: revoke download grants, remove objects and records, preserve permitted audit metadata, and document residual backup retention. Legal holds and jurisdiction rules must be resolved before ingestion.
