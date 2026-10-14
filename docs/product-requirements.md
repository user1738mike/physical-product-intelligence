# Product requirements

Status: proposed product direction, 2026-10-13. No market validation or commercial traction is assumed.

## Initial customer and workflow
The initial intended customer is a warehouse robotics integrator. An organization owner invites members; an analyst records product and packaging revisions and evidence; an engineer configures a versioned handling constraint profile; an assessor runs an assessment; a reviewer inspects evidence, unknowns, and constraint outcomes before exporting the assessment to an integration. Organization administrators manage membership and retention. Read-only viewers inspect authorized results. Platform operators maintain infrastructure without routine access to customer content.

Assessments support handling decisions; they must not assert certification or guarantee robot safety. Physical validation and customer acceptance remain necessary. Numeric thresholds, permissible uncertainty, representative packaging levels, and robot capabilities must be agreed with the customer rather than invented.

## Scope and acceptance
Phase 0 defines architecture, boundaries, risks and decisions. Phase 1 provides configuration, infrastructure, health endpoints, an honest identification page, automated checks and operational instructions. It has no customer accounts, tenant records, uploads, assessments, or integration credentials. Acceptance: architecture documents exist; Compose builds and starts PostgreSQL, backend and frontend; migrations apply; live/readiness checks pass; backend tests, frontend tests, formatting, linting, schema validation and production build pass. Host limitations must be reported rather than treated as passing checks.

Phase 2 introduces identity, organizations, memberships, tenant-scoped authorization and audit events, with adversarial cross-tenant integration tests before any product ingestion. Later milestones add versioned product data, evidence, constraints, reproducible deterministic assessments and exports. Computer vision, physical tests and asynchronous jobs follow when required.

Phase 3 implements the first product API domain: tenant-unique SKUs, immutable complete product revisions, unit/inner/case/pallet profiles, exact metric observations with uncertainty and reference-only evidence provenance. Existing members contribute records; owners/admins control archival. This preserves the current three-role identity model rather than introducing unreviewed analyst/assessor/viewer roles. Product editing screens, captured evidence artifacts, constraints, assessments and exports remain future milestones. Acceptance requires tenant and nested-product isolation, immutable-history and concurrent-revision tests, additive migration checks, validated OpenAPI and a real session/CSRF proxy smoke test.

## Non-functional requirements
All customer data is tenant-scoped, traceable and exportable under policy. Assessments preserve immutable input snapshots, units, uncertainty and rule versions. Private storage is accessed through authorized services. Production configuration fails closed. Initial availability target, service limits and latency SLOs are unresolved; measure actual workflows before promising them. Accessibility targets WCAG 2.2 AA and keyboard navigation; formal accessibility review is pending.

## Open questions and risks
Confirm customer workflow, required packaging hierarchy, constraint semantics, identity provider, jurisdictions, evidence licensing, retention, recovery budgets and safety responsibilities. Integration demand is an assumption. Missing or conflicting measurements must produce explicit unknown outcomes rather than silent defaults. Tenant leakage, malicious evidence, false certainty and mutable rules are primary product risks.
