# Product requirements

Status: proposed product direction, 2026-10-13. No market validation or commercial traction is assumed.

## Initial customer and workflow
The initial intended customer is a warehouse robotics integrator. An organization owner invites members; an analyst records product and packaging revisions and evidence; an engineer configures a versioned handling constraint profile; an assessor runs an assessment; a reviewer inspects evidence, unknowns, and constraint outcomes before exporting the assessment to an integration. Organization administrators manage membership and retention. Read-only viewers inspect authorized results. Platform operators maintain infrastructure without routine access to customer content.

Assessments support handling decisions; they must not assert certification or guarantee robot safety. Physical validation and customer acceptance remain necessary. Numeric thresholds, permissible uncertainty, representative packaging levels, and robot capabilities must be agreed with the customer rather than invented.

## Scope and acceptance
Phase 0 defines architecture, boundaries, risks and decisions. Phase 1 provides configuration, infrastructure, health endpoints, an honest identification page, automated checks and operational instructions. It has no customer accounts, tenant records, uploads, assessments, or integration credentials. Acceptance: architecture documents exist; Compose builds and starts PostgreSQL, backend and frontend; migrations apply; live/readiness checks pass; backend tests, frontend tests, formatting, linting, schema validation and production build pass. Host limitations must be reported rather than treated as passing checks.

Phase 2 introduces identity, organizations, memberships, tenant-scoped authorization and audit events, with adversarial cross-tenant integration tests before any product ingestion. Later milestones add versioned product data, evidence, constraints, reproducible deterministic assessments and exports. Computer vision, physical tests and asynchronous jobs follow when required.

Phase 3 implements the first product API domain: tenant-unique SKUs, immutable complete product revisions, unit/inner/case/pallet profiles, exact metric observations with uncertainty and reference-only evidence provenance. Existing members contribute records; owners/admins control archival. This preserves the current three-role identity model rather than introducing unreviewed analyst/assessor/viewer roles. Product editing screens, captured evidence artifacts, constraints, assessments and exports remain future milestones. Acceptance requires tenant and nested-product isolation, immutable-history and concurrent-revision tests, additive migration checks, validated OpenAPI and a real session/CSRF proxy smoke test.

The Phase 3 completion increment implements the catalog UI and editing flows, live packaging profiles/history, typed reported/estimated claims, authorized documented physical verification and explicit canonical claim selection. This supersedes the editing-screen deferral above. Conflicting observations remain visible; neither a selected estimate nor a manual entry becomes physically verified without a new owner/admin measurement attestation. Evidence artifact capture and independent rights/checksum verification remain deferred. Acceptance additionally includes real browser form/search/pagination/role/error checks and PostgreSQL structural provenance constraints. No Phase 4 compatibility engine, AI extraction, billing or analytics dashboard is included.

## Non-functional requirements
All customer data is tenant-scoped, traceable and exportable under policy. Assessments preserve immutable input snapshots, units, uncertainty and rule versions. Private storage is accessed through authorized services. Production configuration fails closed. Initial availability target, service limits and latency SLOs are unresolved; measure actual workflows before promising them. Accessibility targets WCAG 2.2 AA and keyboard navigation; formal accessibility review is pending.

## Open questions and risks
Confirm customer workflow, required packaging hierarchy, constraint semantics, identity provider, jurisdictions, evidence licensing, retention, recovery budgets and safety responsibilities. Integration demand is an assumption. Missing or conflicting measurements must produce explicit unknown outcomes rather than silent defaults. Tenant leakage, malicious evidence, false certainty and mutable rules are primary product risks.

## Phase 4 ingestion increment

Phase 4 implements bounded CSV/XLSX import, deterministic labeled text PDF/TXT extraction, explicit source mapping, per-attribute review/correction/rejection, new-product approval, provenance/quality/conflict comparisons, private evidence downloads and transactional idempotent application. New values never overwrite canonical data during parsing. Import approval cannot confer physical verification. Acceptance requires upload/tenant/role/parser/idempotency/concurrency tests, PostgreSQL migration preservation, real API/frontend flow checks and explicit remaining production limitations. No compatibility engine, OCR/AI vision, paid model integration or Phase 5 is included.

## Phase 5 compatibility increment

Equipment management, documented specification provenance, immutable rules/activation and deterministic assessments are implemented. Owner/admin manages specifications; all active members assess and inspect history. Explicit packaging level/orientation, qualifying evidence and four hard envelope maxima are required to establish compatible. Reliable hard failure takes precedence; otherwise unresolved required inputs yield indeterminate. Reported, estimated, attested and conflicting evidence remain distinct, and editorial selections cannot conceal conflict. History retains exact snapshots; comparisons never rerun them. This supersedes earlier assessment deferrals. No Phase 6, safety certification or physical handling validation is included. See [guide](compatibility-api.md) and [acceptance report](phase5-completion-report.md).

## Phase 6 AI-assisted intelligence

Existing private documents can produce source-grounded, deterministically normalized candidates for explicit owner/admin review. Candidates preserve originals, source quotes/location, provenance, validation, conflicts and decision history. Approval accepts a reported source assertion, never physical verification; explicit selection and atomic application precede a separately requested deterministic assessment. Core parsing and manual review work while AI is unavailable. No AI compatibility decisions, autonomous tools or Phase 7 scope is included. Acceptance and residual limits are in the [Phase 6 report](phase6-completion-report.md).
