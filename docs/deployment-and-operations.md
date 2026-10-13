# Deployment and operations

## Environments
Compose is local-only: PostgreSQL volume retains development data, application ports bind to 127.0.0.1, database has no published port. Backend waits for a healthy database. Migrations are an explicit command and a separate production release step. Do not use development settings or Compose credentials in production.

Staging and production use separately provisioned managed PostgreSQL, private S3 storage, secret manager and TLS ingress. Build immutable artifacts from lockfiles, run as non-root, set resource limits, and scan base images. Pin image digests when promoting a release; local images use explicit version tags and are not digest-locked. Production frontend uses the standalone server; backend uses Gunicorn. Current Dockerfiles are development foundation artifacts and require platform validation before production promotion.

Required production settings: DJANGO_SETTINGS_MODULE=config.settings.production, DJANGO_SECRET_KEY (50+ characters and non-placeholder), POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, DJANGO_ALLOWED_HOSTS (no wildcards), DJANGO_CSRF_TRUSTED_ORIGINS (HTTPS). DJANGO_TRUST_PROXY=true is allowed only behind an ingress that strips incoming X-Forwarded-Proto and supplies its own. Run manage.py check --deploy under real injected settings; never silence findings blindly. Serve collected static files separately if later added; private evidence must never be mounted there.

## Health and telemetry
GET /api/v1/health/live/ returns process status. GET /api/v1/health/ready/ executes SELECT 1 and returns 503 without database details on failure. GET /health on frontend checks its own server only. Readiness does not assert pending migrations or customer workflow readiness; release smoke checks migrations separately. Backend requests emit JSON with bounded request ID, status and milliseconds; collect stdout with access-controlled retention. The error-reporting provider, metrics exporter, alert destination and log retention are unresolved deployment choices. Alert on sustained readiness failures, elevated 5xx, p95 latency, disk/database saturation and backup failures once baselines exist.

## Release and recovery
Review migration compatibility, take a verified backup, apply migrations once, roll out API/frontend, run health and authenticated workflow smoke tests. Use expand/contract migrations for rolling releases; rollback code only when schema remains compatible. Forward-fix destructive migrations. No automated rollback or hosted deployment is implemented.

Provisional recovery expectations for customer launch: RPO <= 24 hours and RTO <= 8 hours, subject to customer approval and budget. Configure encrypted daily backups and PostgreSQL PITR, separate backup access, object versioning where retention permits, and quarterly restore drills. These are requirements, not verified capabilities. Record restore duration and integrity checks against tenant counts and evidence checksums. Backup retention provisionally 30 days; legal/customer review is required. For local backup: docker compose exec -T db pg_dump -U ppi -d ppi --format=custom --file=/tmp/ppi.dump, then docker compose cp db:/tmp/ppi.dump ./artifacts/ppi.dump after creating artifacts. A local backup is sensitive and ignored by Git. Restore into a separate empty database; never test recovery against live production.

## Incident response
Identify incident owner, isolate compromised credentials, preserve redacted logs/audit evidence, assess tenant exposure, notify under agreed contracts, restore safely and document corrective actions. Onboarding, access reviews, retention/legal holds, key rotation cadence, on-call staffing and regional data residency remain launch decisions.
