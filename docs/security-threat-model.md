# Security threat model

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
Phase 1 implements required production configuration checks, secure settings, denied-by-default DRF permissions, JSON operational logs, generic readiness errors and loopback-only application bindings. There is no implemented customer authentication, tenant isolation, audit retention pipeline, malware scanner, encrypted bucket or disaster-recovery system yet. Django migration tables and framework auth tables do not constitute the customer identity design.

Secrets belong in environment injection from a production secret manager; .env is local-only and ignored. Never put secrets in NEXT_PUBLIC variables or log bodies/headers. Private storage must remain separate from static assets. Separate development, staging and production identities, databases, buckets and keys. Retention and deletion must cover primary data, replicas, objects, logs and backups; legal policies remain unresolved. Review OWASP ASVS controls before customer launch and commission an independent penetration test before enterprise use.
