# Domain model

Organization, Membership and AuditEvent are implemented in Phase 2; User remains Django's migration-safe global `auth.User`. Phase 3 implements Product, ProductRevision, PackagingProfile, Measurement, Evidence and immutable RevisionEvidence links. Phase 5 implements equipment constraints and assessments as detailed below; external integrations remain planned. Tenant entities use UUIDs and UTC timestamps. Measurements use exact decimals; tenant ownership is derived through the product at every boundary.

Phase 3 completion adds PackagingConfiguration (stable editable identity), ConfigurationRevision (immutable descriptor/lifecycle history), AttributeClaim (typed immutable numeric/text assertion), ClaimVerification (authorized physical attestation linking original and measured claims), and ClaimSelection (immutable canonical decision/rationale). ADR 0008 defines their boundaries. Existing bundled PackagingProfile snapshots remain compatible and immutable; they are not the current editable configuration collection.

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
Product PATCH copies retained snapshot data and appends a revision with optimistic concurrency. Live packaging edits/lifecycle transitions also require expected versions and record prior descriptors. Numeric claims reuse exact metric normalization; text claims use an allowlisted attribute vocabulary and cannot carry numeric units. Reported and estimated claims are directly contributable; measured claims require an owner/admin physical attestation with source, procedure, instrument, time and limitations. Selecting an estimate never changes its basis. New contradictory claims make an earlier selection stale. Unknown is the absence of a claim; no preferred value is invented.

PostgreSQL deferred constraint triggers validate same-product source/claim/profile links, ordered same-revision bundled containment and verification consistency; a measured claim requires its verification record by commit. SQLite does not install these guards. History remains protected by application/ORM/admin controls and foreign keys; no RLS or database-level immutability is claimed.

All tenant-owned foreign key relationships must be checked for same-organization ownership inside transactions; a UUID does not grant access. Add database constraints where feasible, including tenant-specific revision uniqueness. Deletion uses retention-aware workflows: revoke download grants, remove objects and records, preserve permitted audit metadata, and document residual backup retention. Legal holds and jurisdiction rules must be resolved before ingestion.

## Phase 4 ingestion increment

Ingestion adds ImportJob (tenant, private file key/checksum, lifecycle/options/mapping/preview/counters), ImportRow (immutable-through-API source cells/location and versioned catalog targets), Candidate (raw/proposed/normalized attribute, quality/comparison, reviewed decision and resulting claim), and append-only ReviewRecord (corrections/decisions/mapping/creation actor/time/reason). Applied rows reference the existing Evidence model and captured source via the job. Numeric claims reuse metric-v1 and remain reported; selection is explicit and never confers verification. Ordinary APIs cannot edit raw uploads/rows or delete review history. Source/artifact integrity does not prove authenticity.

## Phase 5 implemented entities

The planned ConstraintProfile/ConstraintVersion terminology above is implemented as Equipment (stable tenant/code identity), EquipmentRevision (immutable numbered definition), RuleSet (immutable numbered typed rules bound to a specification), RuleActivation (immutable approval) and Assessment (immutable actor/time/target revisions, full inputs, provenance, exact rules and per-rule output). Parent assessments must share product/package/equipment targets. Organization/request UUID uniqueness supplies retry safety. No separate ConstraintOutcome rows are needed: bounded detailed results are captured inside the immutable assessment JSON. See [compatibility API](compatibility-api.md). These implemented records supersede the constraints/assessment deferral in the historical introduction.

## Phase 6 extraction increment

ImportJob now distinguishes deterministic uploads and AI extraction jobs, with a protected original-source reference, tenant/request identity and bounded operational metadata. Candidate retains extraction provenance/quote/schema/model and original validation state. ImportRow and immutable ReviewRecord remain the target/review boundary; no duplicate evidence, candidate or assessment models are added. Assessment evidence snapshots now carry extraction metadata. See [AI guide](ai-extraction-api.md) and ADR 0011.
