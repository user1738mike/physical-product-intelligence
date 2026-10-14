# Phase roadmap

Phase 1: foundation implemented; its normal Docker startup verification remains open because host address pools were exhausted. Preserve volumes and other projects' networks when resolving that blocker.

Phase 2: identity, session/CSRF authentication, organizations, owner/admin/member services, membership-derived tenant boundaries, audit history, reviewable migrations and account/organization frontend implemented. Native PostgreSQL tests and frontend checks are recorded in [the execution report](../phase2-implementation-report.md). Acceptance requires the report's final checks and explicit review of remaining runtime/deployment limitations.

Deferred within identity operations: email verification/invitations, recovery, MFA/SSO, distributed abuse controls, privileged audit archival/purge and immutable retention sink. These are launch decisions, not implemented features. Operator provisioning is explicit through Django's trusted admin mechanisms. Production requires a verified shared TLS ingress, origin/header policy and backups.

Phase 3: structured product identities with tenant-unique SKUs, immutable numbered revisions, packaging hierarchy snapshots, exact metric observations/uncertainty, reference-only evidence provenance and tenant-scoped APIs are implemented. See [API guide](../product-api.md), ADR 0007 and [execution report](../phase3-implementation-report.md). All existing roles may contribute product data; owner/admin controls archival. New evidence and revisions cannot change prior snapshots. Membership revocation, tenant suspension, cross-product provenance denial and concurrent revision allocation are tested.

Next domain work: product editing UI, evidence file capture/private storage/quarantine/verified checksums, configurable constraints and deterministic assessments. Uploads, extraction, assessments, rule execution and exports are not implemented. Production TLS/ingress, abuse limits, retention/deletion and Docker runtime acceptance remain open release gates.
