# Security threat model

Completion identity/runtime controls: customer password change reauthenticates;
operator-assisted recovery uses a fifteen-minute, one-way-verifier grant bound
to the current password, single-use under a user row lock. New issuance revokes
earlier links. Customer recovery excludes privileged accounts and inactive users.
Issuance requires an active operator and protected owner DB connection; PostgreSQL
denies HTTP-role issuance or historical rewrites. Links leave the command only
through an exclusive 0600 file in an owner-only Linux directory. Identity proof
and private delivery remain trusted support responsibilities, never inferred
from unverified email or organization-admin status. The browser removes the URL
fragment immediately; CSRF, shared throttling and generic errors protect POST
redemption. Password updates invalidate sessions and revoke issued integration
credentials. In-flight requests already admitted cannot be recalled.

Organization settings expose existing server permissions through real customer
forms; client role visibility is presentation only. Ownership transfer and
suspension require explicit typed intent; server transactions preserve the sole
owner and check membership/activity again. Suspended organization recovery exposes
reactivation only to its existing owner. Audits remain protected and paginated.

Supervised processors hold the protected operator connection, never the HTTP
identity. They execute bounded existing delivery/recovery services with leases
and live tenant/issuer/entitlement checks, never upload instructions, live AI
processing or implicit payment initiation. Containers mount no evidence/backups,
run without root/capabilities on a read-only filesystem and emit numeric counts.
Worker health requires a successful recent cycle. Maintenance must quiesce every
writer, including processors; the release helper now enforces this for new
supervised rehearsal manifests. Runtime starts/stops, interrupted claims, stale
extraction fences, revoked operators and quiesced backup selection have regression
coverage. Host monitoring/egress, support identity proof and real deployment
acceptance remain separate operational requirements.

Assets: tenant product data, evidence, constraint IP, reproducible results, credentials, audit history and backup data. Actors: authorized users, malicious tenants, anonymous attackers, compromised workers and privileged operators. Trust boundaries: browser/ingress, ingress/application, application/database, application/storage, third-party identity/integration and operators/production.

| Threat | Required mitigation and verification |
| --- | --- |
| Cross-tenant object access | Membership-derived context, scoped queries/related lookups, deny-by-default roles; test list/detail/update/export/job paths with two tenants |
| Session/token theft | Verified identity flow in Phase 2; CSRF, secure cookies, short expiry, rotation and revocation; do not expose tokens in logs |
| Injection and malicious files | ORM parameterization, strict serializers, upload size/type limits, quarantine, isolated parsers; no public upload storage |
| SSRF via evidence URL | Defer URL fetching; later allowlist destinations and block private/link-local networks across redirects and DNS resolution |
| False assessment certainty | Immutable snapshots, uncertainty and unknown outcomes, versioned rules; review boundary and conflict cases |
| Audit tampering | Append-only service permissions; ship to separately controlled retention sink; operator access audited |
| Resource exhaustion | Ingress limits, pagination, quotas, job concurrency/retry bounds; load and abuse tests before launch |
| Supply-chain compromise | Exact dependencies, npm lockfile, Python lock, CI checks and scheduled patch review; scan releases before deployment |
| Misconfiguration | Production fail-closed settings; explicit proxy trust; no public database port; deployment security checks |

## Implemented controls and limits
Phase 1 production configuration checks, secure settings, denied-by-default DRF permissions, sanitized request logs, generic readiness errors and loopback-only bindings remain. Phase 2 implements username/password identity on the existing Django user model, CSRF-protected sessions, current membership/role authorization, scoped nested queries, transactional ownership and append-only audit APIs. Username registration does not verify an email address or grant staff privileges. An active membership is required even for staff. Suspended organizations block protected operations, and membership removal immediately affects subsequent requests.

Sessions are HttpOnly, SameSite=Lax, eight-hour absolute expiry and production Secure; logout flushes the session, password changes/deactivation revoke authentication, and login rotates unauthenticated sessions. All mutations, including anonymous login/register, require CSRF. No auth secrets are stored in localStorage. TLS/shared-origin routing, trusted-origin review and stripped proxy headers are mandatory for production. DRF local-memory throttles are best-effort; distributed ingress limits, signup abuse controls, recovery/MFA/SSO, dependency review and independent penetration testing remain launch work.

Audit records contain actor/tenant IDs, fixed action/outcome/target fields and allowlisted role metadata. They exclude passwords, raw authentication headers, cookies, tokens, IPs and submitted usernames. Owners/admins can read only their own active organization's history; ordinary members cannot. Success events roll back with failed writes. Denied API attempts and failed authentication are separate failure events. There are no edit/delete APIs and admin pages are read-only. ORM guards are not database-level tamper protection: operators/DB owners remain trusted. Organization deletion is blocked by audit references; deleting an unassociated actor nulls its audit reference. A separately controlled immutable sink and monitored operator-access process remain required for customer launch. Provisional retention is 365 days pending legal/customer review; no automatic purge is implemented.

No audit retention pipeline, malware scanner, encrypted bucket or disaster-recovery system is claimed. PostgreSQL RLS is not configured. Audit failure causes protected business writes to roll back; availability monitoring is necessary. HTTP security outcomes and data invariants are tested, including PostgreSQL ownership concurrency; production TLS/proxy behavior still needs staging validation.

Phase 3 scopes every product/revision/evidence/packaging lookup through current membership and its authorized product. Foreign evidence references are rejected even between products in one organization. All roles may contribute records; only owners/admins archive products. Product writes share organization locks with membership changes and product locks for sequential revision allocation. History and provenance are immutable through supported services/API; read-only admin and ORM guards are supplemental, not protection against raw SQL or trusted operator writes. Tenant identity is derived through product foreign keys; same-product cross-table invariants are enforced by transactional services rather than DB triggers.

Evidence is reference-only metadata. Declared digests, source references and contributor-declared licenses are unverified; no file or URL fetching, object-storage access, malware inspection or verified artifact capture occurs. There is no evidence download API. Decimal unit validation prevents dimension mixing and silent loss of accepted precision; missing or conflicting observations never produce inferred safety results. Collections are paginated, nested input lists bounded, and the existing proxy bounds body size. Tenant quotas, dedicated product throttles, load testing and retention-aware correction/deletion workflows remain launch work.

Secrets belong in environment injection from a production secret manager; .env is local-only and ignored. Never put secrets in NEXT_PUBLIC variables or log bodies/headers. Private storage must remain separate from static assets. Separate development, staging and production identities, databases, buckets and keys. Retention and deletion must cover primary data, replicas, objects, logs and backups; legal policies remain unresolved. Review OWASP ASVS controls before customer launch and commission an independent penetration test before enterprise use.

Phase 3 completion adds stable packaging identities, immutable descriptor revisions and typed immutable attribute claims. Reported/estimated creation cannot accept a measured basis, arbitrary confidence score, actor, verification timestamp or ownership fields. Physical verification is owner/admin-only and requires a same-product physical_test source, instrument, procedure, observation time and measurement limitations. It creates a separate measured claim and immutable verification; the original estimate remains unchanged. Selection requires owner/admin rationale and never changes source basis. New contradictory observations invalidate the current canonical selection. These are authorized attestations, not independently verified artifact bytes or safety results.

PostgreSQL migration 0003 adds deferred constraint triggers for same-product source/claim links, same-revision ordered containment, claim/profile ownership, and physical-verification scope/record consistency. They supplement transactional API checks; no RLS or database history immutability is claimed. SQLite does not install these guards. All new list/detail/mutation/history routes reuse Phase 2 membership checks. History exposes only success records scoped to the authorized product/profile; members do not gain global audit access. Stale edits return 409. Input lists, body sizes, query choices and attribute claim counts are bounded. Browser forms preserve decimal strings, provide distinct quality states and error focus, and store no session secrets in localStorage.

## Phase 4 ingestion increment

Phase 4 adds authenticated private uploads, tenant-scoped download/job/candidate/report routes, server-generated object keys, server-computed checksums, bounded multipart bodies, retained-storage quotas, parser subprocess timeouts, Linux memory/CPU limits, hardened XML and ZIP expansion/relationship restrictions. Formula/macro content is never executed. Source content never becomes prompts/tools/configuration. Owner/admin review and explicit creation/canonical selection precede atomic application; stale catalog targets invalidate approval, and retries reuse completed results. Source claims remain reported and original evidence/history persists. Production fails closed for unscanned uploads/sources unless a trusted scanner returns clean; development/test unscanned uploads carry a visible label. No scanner engine, complete OS sandbox, encrypted cloud bucket, durable worker, retention/orphan cleanup, RLS or independently authenticated supplier truth is claimed. See ADR 0009 and the ingestion guide for residual risks and deployment gates.

## Phase 5 assessment threats and controls

Forged tenant/nested references are denied using current membership, scoped lookups and shared organization transaction locks. PostgreSQL deferred triggers backstop equipment/specification/rule and assessment product/package/revision/parent ownership. These are not RLS; privileged operators remain trusted. Allowlisted typed rules execute no expressions or code. Payload/rule/claim bounds and a best-effort per-process collection throttle bound ordinary work; distributed ingress controls remain required. Idempotency keys cannot be changed to reinterpret a prior result. Frozen JSON preserves conflicting claims, original units, evidence, rule operands and explanations; normal ORM/API mutation/deletion is blocked. Estimates and known AI equipment evidence cannot authorize unsupported pass/activation paths. Source references remain unverified attribution, not manufacturer authenticity. Private downloads retain Phase 4 authorization; links never grant access themselves. Hard failures override unresolved checks; partial specifications never imply unlimited capacity. Complete static fit is distinct from hardware safety. See [semantics and limits](compatibility-api.md).

## Phase 6 external inference boundary

AI is disabled by default and server-configured only. Explicit processing sends bounded private source text to the fixed configured provider; operators must approve transmission/retention policy. Untrusted document data is separated from extraction instructions; no model tools, environment variables, tenant authority or arbitrary URLs/models are accepted. Exact source quote/segment and literal value/unit checks plus deterministic normalization quarantine unsupported/unknown output. Prompt injection and semantic misattribution remain possible, so approval/canonical selection is human-controlled. Tenant scopes, source checksums/scanning, PostgreSQL source/target guards, optimistic reviews and leased finish transactions remain authoritative. Estimates are never upgraded to measured facts and completed assessments/rules remain unaffected. Provider errors are fixed categories; SDK diagnostics are suppressed. See [AI privacy and limits](ai-extraction-api.md).

## Phase 7 deployment boundary

The earlier per-process throttling limitation is superseded by shared atomic PostgreSQL write/processing limits and global extraction admission. Only verified organization membership selects tenant counters; untrusted forwarding cannot change peer/scheme authority. Production requires exact hosts/HTTPS origins, verified database TLS, restricted proxy peers, non-owner/non-administrative runtime DB role and private storage/scanner policy. Outages fail closed; fixed-window bursts, database contention, operator trust and ingress DDoS protection remain explicit risks. Private ClamAV hook rejects outages/infection; actual scanner/signature deployment is unverified. Structured logs omit private content and raw URLs. Backup bundles remain sensitive trusted inputs requiring encryption/ACLs; restore only targets a new empty isolated DB/root. No live provider, data deletion, automatic file migration or production deployment occurred. See the [operations guide](deployment-and-operations.md) and [release blockers](phase7-completion-report.md).
