# Domain model

These are planned entities, not Phase 1 database tables. Use UUID external identifiers, UTC timestamps and decimal measurements; maintain tenant ownership at every boundary.

| Entity | Relationships and invariants |
| --- | --- |
| Organization | Tenant boundary; lifecycle and retention policy |
| User / Membership | Global identity; membership joins user to organization with explicit role; unique pair |
| Product / ProductRevision | Organization-owned product; immutable numbered revisions, source and author |
| PackagingRevision | Belongs to product revision; nested packaging level (unit/case/pallet), counts and parent validation |
| Measurement | Revision, property, decimal value, canonical unit, original value/unit, method, time, source evidence, uncertainty bounds |
| Evidence | Organization, checksum, private object key or source reference, author, observed/ingested timestamps, consent/license, quarantine status |
| ConstraintProfile / ConstraintVersion | Organization-owned profile with immutable rule versions and applicability to packaging level |
| Assessment / ConstraintOutcome | Organization, input revision snapshot, constraint version snapshot, evaluator version, output, provenance and reviewer |
| AuditEvent | Organization or system scope, actor, action, target, timestamp, request ID; append-only service interface |
| IntegrationCredential | Organization-scoped credential digest, scope, expiry and revocation; raw token shown once |

## Provenance and reproducibility
Measurements retain original and canonical representations. Define a reviewed unit vocabulary and dimension-safe conversions (e.g. mass versus force); reject ambiguous units. Precision, uncertainty, observation method and sample population remain explicit; unknown is distinct from zero. Conflicts retain competing observations and the rationale for selecting one. Do not infer missing data without a recorded method and confidence.

Published assessments reference immutable revisions and serialize complete normalized input, rules, engine version, evidence hashes, unit conversion version, execution timestamp and decision policy. Use pass/fail/unknown/not-applicable outcomes with reasons and per-rule evidence links. Re-running changed rules creates a new assessment. Constraints with uncertain ranges require a documented conservative boundary policy. Mutable external URLs alone are insufficient evidence. Physical test results and model inference outputs need their own versioned methods and artifacts later.

## Integrity and deletion
All tenant-owned foreign key relationships must be checked for same-organization ownership inside transactions; a UUID does not grant access. Add database constraints where feasible, including tenant-specific revision uniqueness. Deletion uses retention-aware workflows: revoke download grants, remove objects and records, preserve permitted audit metadata, and document residual backup retention. Legal holds and jurisdiction rules must be resolved before ingestion.
