# System architecture

## Modular monolith
Next.js renders the public foundation page. Django/DRF owns the API and application services; PostgreSQL is the authoritative database. Deploy frontend and API behind one TLS ingress using /api/v1 routing to avoid broad CORS. Compose is local development infrastructure, not a production deployment recipe. No microservices or Kubernetes are required.

Planned backend modules: identity (users and external identities), tenancy (organizations and memberships), catalog (products and packaging revisions), evidence (source metadata and private storage), constraints (versioned handling profiles), assessments (deterministic evaluation and snapshots), audit (security and data mutations), integrations (tenant-scoped tokens and exports). Only the operations module is implemented in Phase 1. Modules exchange service calls and immutable identifiers, with explicit tenant context; no arbitrary cross-module model writes. Define transactional boundaries around revision creation and assessment publication.

## API and isolation
All customer endpoints will live under /api/v1/ and use DRF with an OpenAPI contract. Additive changes are preferred; breaking changes require a new major version and a published deprecation window. Health and schema endpoints expose no customer data. DRF denies access by default; only explicitly public operations are anonymous. Session authentication remains a framework primitive, not an implemented sign-in flow.

Phase 2 will resolve organization membership on every request, enforce role permissions in service methods, and scope every query and related-object lookup by organization. Organization identifiers supplied by callers are never authority. Composite tenant/object uniqueness constraints and cross-tenant negative tests are mandatory. PostgreSQL row-level security is deferred pending a verified connection/transaction tenant-context design; application isolation must be proven first. Platform admin bypass is not provided by Phase 1.

## Storage and jobs
The evidence module will own a private S3-compatible storage adapter, opaque object keys, encryption, checksums, upload limits and short-lived authorized download grants. No media URL or public bucket is configured now. Quarantine and malware inspection precede evidence availability. Introduce Celery/Redis when ingestion or assessment workflows need durable background work; use idempotency keys, retry limits and transaction-on-commit dispatch. An outbox may be required before externally delivered events.

## Observability and configuration
JSON request logs contain request identifiers, method, path without query strings, status and duration; they exclude request bodies, headers and secrets. Client-supplied request IDs are validated. Liveness checks the process; readiness executes SELECT 1 and returns a generic failure. Metrics are an internal authenticated/scraped ingress concern: derive request counts, latency and error rate from logs initially; dedicated exporters and error-reporting providers are integration points, not installed integrations. Health traffic must be rate limited at ingress.

Development permits HTTP on loopback. Testing uses PostgreSQL in CI/Compose, with opt-in SQLite unit smoke tests only. Production requires secrets, explicit hosts and trusted HTTPS CSRF origins, enforces secure cookies/HSTS/TLS redirect and never enables debug. TLS proxy header trust is opt-in and requires ingress to strip forged client headers.
