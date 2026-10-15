# Deployment and operations

The [Phase 7 report](phase7-completion-report.md) distinguishes executed checks from release requirements. These procedures do not authorize deployment, destructive maintenance, or a provider call.

## Local Compose and network recovery

Preserve an existing `.env`; `python scripts/setup_env.py` creates development credentials only when that file is absent. Never use development settings/credentials in production. PostgreSQL has no published port and application ports bind to loopback. Set `PPI_BACKEND_PORT=8001` when another application owns 8000, and `PPI_SMOKE_BACKEND=http://127.0.0.1:8001` for the direct health smoke. Keep frontend 3000 for the supplied scripts/development CSRF origins.

```powershell
docker compose up --build -d db backend
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py migrate --check
docker compose up --build --wait --wait-timeout 240
python scripts/phase2_smoke.py --allow-create-test-data
python scripts/phase3_smoke.py --allow-create-test-data
python scripts/smoke.py
docker compose stop
```

Migrations must precede readiness: startup does not apply them. Smoke scripts create and retain synthetic records; run only on a disposable database. Phase 3 also invokes ingestion, compatibility and AI-disabled smoke checks. Registration is limited to five/hour per peer; repeated smoke runs can correctly return 429. Do not reset working counters to bypass this. Ordinary stop/start preserves DB/evidence. Never use volume deletion, database reset, prune or unrelated network deletion as troubleshooting steps.

For local verification with production application servers, add `-f compose.runtime-check.yaml` after `-f compose.yaml` to every command. It selects Gunicorn and standalone Next, retaining development settings and local HTTP; it is not a production TLS test. On Linux development bind mounts, set `PPI_CONTAINER_UID`/`PPI_CONTAINER_GID` to the checkout owner's non-root IDs for upload permissions. Production uses image UID 10001 and private persistent storage, without a source bind mount.

For exhausted Docker address pools, inspect actual `docker network ls`, IPAM fields from network inspection, and host LAN/VPN/WSL routes first. Do not print container environments. Create `artifacts` if absent, then:

```powershell
python scripts/compose_network.py --output artifacts/local-network.json
docker compose -f compose.yaml -f artifacts/local-network.json config --quiet
docker compose -f compose.yaml -f artifacts/local-network.json up -d db backend
```

Append the same override to subsequent commands, including migrations and stop/start. The helper inventories Docker/host routes and exclusively writes a project-only non-overlapping RFC1918 /24; it refuses missing routes, collisions and overwrite. It changes no Engine defaults and deletes nothing. Inspect before use and revalidate after VPN/LAN changes; do not hardcode this host's chosen range elsewhere. Existing network conflicts require a planned operator maintenance change, not automatic deletion/recreation.

## Production recipe, configuration and ingress

`compose.production.yaml` is a separate recipe, not an override of development Compose. It provides non-root immutable application images, read-only roots, tmpfs/CPU/memory/PID bounds, dropped capabilities, no host ports and graceful shutdown. It does not provision managed PostgreSQL, ingress, a scanner daemon, backup encryption or production infrastructure. Build frontend with `--target production`; backend accepts `INSTALL_AI=false` or `true` for the optional pinned SDK. Scan images and pin reviewed digests when promoting a release. No image publication/deployment occurs in Phase 7.

Set `PPI_BACKEND_IMAGE`, `PPI_FRONTEND_IMAGE`, `PPI_API_BACKEND_ORIGIN` and `PPI_PRODUCTION_ENV_FILE`. The latter is a protected secret-manager materialization outside the repository, injected only into backend. Never pass backend secrets to frontend or Docker build args. Required backend settings:

| Setting | Policy |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | Recipe forces `config.settings.production` |
| `DJANGO_SECRET_KEY` | 50+ strong non-placeholder characters; shared across API instances for sessions/HMAC limiter identities |
| `DJANGO_ALLOWED_HOSTS` | Exact actual hostnames; no wildcard, leading-dot suffix, URL or port |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact HTTPS browser origins |
| `POSTGRES_DB/HOST/PORT` | Provisioned private PostgreSQL with encrypted storage |
| `POSTGRES_USER/PASSWORD` | Separate non-owner runtime DML role; strong non-default password of at least 24 characters |
| `POSTGRES_SSLMODE` | `verify-full` only (default); mount `POSTGRES_SSLROOTCERT` read-only for private CA if needed |
| `DJANGO_TRUST_PROXY` | `true` only with restricted actual peer `TRUSTED_PROXY_CIDRS` and ingress header stripping |
| `INGESTION_STORAGE_ROOT` | Absolute private path outside static; recipe fixes `/var/lib/ppi/private` |
| `INGESTION_SCANNER` | Recipe selects `ingestion.scanning.clamd_scan`; requires private `CLAMD_HOST`, optional `CLAMD_PORT` (3310 default) |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS/PRELOAD` | Explicit opt-ins only after domain-wide prerequisites are verified; otherwise review corresponding deployment-check warnings |

Recommended ingress routes same-origin `/api/v1/` directly to Django and other paths to Next. It strips untrusted forwarding headers and sets canonical `X-Forwarded-Proto` and `X-Real-IP`, enforces upload/header/connection bounds and restricts backend reachability to trusted peers. Next's fallback proxy deliberately does not pass arbitrary scheme/client-IP headers; its production `API_BACKEND_ORIGIN` must therefore be a validated internal **HTTPS** API origin, with a Node-trusted certificate, allowed Django Host and routing that cannot proxy back to itself. Plain HTTP fallback to SSL-redirecting Django causes redirects and is unsupported. Fallback authentication peer limits aggregate at Next's peer; direct ingress API routing is required for per-client peer limits. Test forwarded-header spoofing and real routing in staging. Ingress joins the platform's private network; recipe exposes no host backend/DB port.

Run `python manage.py check --deploy --fail-level WARNING` under actual injected settings. `python scripts/check_production_config.py` validates only synthetic HTTPS settings, without real database/provider connectivity. The production container health check exercises readiness internally; external TLS readiness and certificate checks remain required. Production readiness rejects pending migrations, elevated/owner runtime DB roles, absent private root or scanner configuration. Scanner configuration does not establish daemon reachability: uploads reject scanner outages separately.

Standalone Next includes its built static assets. If Django admin is exposed to trusted operators, collect its static files into a separate reviewed artifact/ingress location and restrict `/admin/`; never serve the private volume as static/media content.

## Database roles, migration and rollback

Review SQL on a representative clone and back up before applying migrations once, then run `migrate --check` before rolling out API/frontend. Phase 7 adds only the operational counter table; provenance/immutable snapshot semantics remain unchanged. Use a separate migration role owning schema objects; release-job credentials must not reach runtime. Runtime needs CONNECT, schema USAGE, table DML and sequence USAGE/SELECT, but no public CREATE, object/database ownership, administrative flags or membership allowing owner assumption. Revoke default public schema CREATE where necessary. Apply matching `ALTER DEFAULT PRIVILEGES FOR ROLE <migration_role> IN SCHEMA public` grants for future objects. Review grants per table, particularly audit/snapshot immutability, and test triggers with the exact runtime identity in staging.

`operational_status` reports privilege/ownership without disclosing role identities. Development's DB owner is intentionally flagged privileged and is not production-ready. No production grant changes were executed here. Use expand/contract migrations; roll back code only if old code supports the migrated schema. Forward-fix destructive migrations. Never automatically reverse migrations or restore over a working database.

## Synchronous processing and shared limits

Small initial deployments retain explicit bounded synchronous processing: Gunicorn 2 workers × 2 threads, DB-wide AI cap 2 across instances sharing PostgreSQL, one fresh extraction per tenant. `AI_EXTRACTION_MAX_CONCURRENT` is bounded 1–8. Parser and source sizes, provider output, and container resources are bounded. Provider timeout is 8 seconds, no SDK retries, output ≤2,500 tokens and AI text ≤24,000 characters. Next aborts upstream waits after 30 seconds; backend may still finish after disconnect. Gunicorn timeout 60 seconds and graceful timeout 45 are worker policies; gthread heartbeat is not a hard per-request thread kill. Production stop grace 65 permits draining. Measure realistic workloads before increasing capacity; no throughput/SLO claim is made.

PostgreSQL stores job state, attempts, lease and review history. A transaction advisory lock serializes global admission, with row locks/lease tokens preventing duplicate final persistence; no DB lock spans provider work. After 90 seconds, interrupted jobs can be reclaimed by explicit process/retry using the latest version. Permissions, source integrity and target state are revalidated before applying. Transient failures have at most three total attempts; permanent errors need corrected source/new extraction. No automatic polling/retry timer/queue consumer/recovery daemon exists. Operator reviews stale jobs, determines whether old work could still be active, then retries through the authorized API. Cancellation revokes persistence but cannot undo an external request/bill. Exactly-once billing/execution is not guaranteed. Introduce a durable queue only when measured capacity or autonomous recovery requirements justify it.

Shared fixed windows use atomic PostgreSQL upserts and HMAC subject keys. Authentication limits use trusted peer: login 10/minute, registration 5/hour. Import writes 120/hour, assessment creation 60/hour, extraction writes 20/hour use user **and authorized organization**. Membership is checked before selecting the organization counter. Bounded paginated GETs are not charged to write scopes. Counter admission rolls back if any subject is denied; 429 includes Retry-After. DB admission failure returns sanitized 503 and fails closed. Fixed windows allow boundary bursts; this is not DDoS protection. Instances need the same DB/secret, trusted proxy policy and synchronized clocks. Add ingress admission/connection limits and monitor DB contention. No password reset, export or unbounded search endpoint exists to limit.

`python manage.py prune_rate_buckets` is dry-run by default; schedule `--apply` only for expired operational counters after policy review. It cannot delete catalog/audit/evidence. No working-data pruning occurred in Phase 7.

## Private files, scanning and retention

Private storage has no public URL/media route. Downloads require authenticated tenant/nested-job authorization and integrity/scan policy; filenames never select storage paths. Signature/UTF validation, extension/MIME allowlists, bounded handlers, ZIP expansion/ratio/entry limits, page/row/cell bounds and format parsing complement each other. None is malware scanning. Existing parser temporary-file/process cleanup remains in use; Linux resource caps add OS enforcement not available identically on Windows.

ClamAV INSTREAM adapter sends ≤2 MiB with a single five-second deadline and bounded response. Only a complete clean reply passes. Infection/error/timeout/unavailability rejects before storage. Provision a private updated clamd service, signature freshness/health monitoring and matching INSTREAM limits, with no public port. Phase 7 mocks clean/infected/timeout/unavailable responses; no daemon/signature freshness is claimed. Readiness validates configuration only; verify real availability through a synthetic staging upload. Unscanned development files cannot silently satisfy production scan policy.

Recipe uses an encrypted/access-controlled persistent filesystem volume: this is **single-host storage**. Multiple hosts require a tested shared private filesystem or an implemented object-storage backend. Current recovery/readiness use filesystem `.location`; S3 is not implemented. No existing private file is migrated automatically. There is no customer-data deletion/retention executor. Retain evidence while claims/candidates/assessments depend on it; agree tenant retention, legal holds and coordinated DB/file/audit deletion before launch. Review orphan/failed uploads; do not silently expire referenced bytes. Backups retain deleted information until separately approved expiry.

Proposed policies needing customer/legal approval: encrypted daily backups plus managed PITR, 30-day backup/log retention (audit retention separately agreed), quarterly isolated restore drills. RPO ≤24 hours and RTO ≤8 hours are requirements, not achieved service commitments. Encryption, PITR, signature freshness and retention execution are release gates. Never publish dumps, source bytes or backup manifests as CI artifacts.

## Backups and isolated restore

Use matching PostgreSQL tools (client major >= server major). Quiesce **all** writers/admin/jobs throughout database/private-copy/count collection; command cannot enforce the maintenance window. Backup exclusively creates a protected directory, custom pg_dump without owner/ACL, original deterministic upload bytes and manifest containing counts, file sizes/checksums and dump SHA-256. It includes sensitive tenant data, password hashes and sessions. Encrypt in approved storage with restricted access. POSIX modes 0700/0600 are set; Windows requires equivalent NTFS ACLs explicitly because chmod does not create a private ACL. Manifest checksums detect corruption but do not authenticate an untrusted bundle.

```powershell
# Inject source DB/private-root settings in a protected maintenance environment:
python manage.py backup_bundle --maintenance-window --confirm-database <exact_source> --output <new_protected_directory> --pg-dump <matching_executable>
# FIRST inject a NEW empty isolated target DB and NEW private-root settings:
python manage.py restore_bundle --bundle <trusted_bundle> --confirm-target-database ppi_restore_<unique_suffix> --media-target <new_configured_root> --pg-restore <matching_executable>
```

Restore refuses source/working DB names, nonempty DB, existing private destination, traversal and checksum mismatch; there is no clean/overwrite mode. Root must match configured storage. It restores schema/data, compares all model counts (ephemeral rate counters excluded), copies private objects and reopens every original upload with normal integrity/scan rules. Partial targets stay quarantined, never automatically deleted/promoted. Apply separate runtime grants because no-owner/no-acl intentionally excludes production role ownership/privileges. Verify tenant/API access, provenance/snapshots and private downloads before promotion.

Reproduce the synthetic drill only on an explicitly selected **disposable local PostgreSQL server** with CREATE DATABASE privilege and matching tools:

```powershell
python scripts/verify_restore.py --allow-create-isolated-data --pg-bin <PostgreSQL_bin_directory>
```

It creates two unique databases/new artifact roots, seeds synthetic tenant/catalog/claims/rules/assessment/private-upload records, migrates, backs up, restores and verifies counts, bytes and authorized/foreign API reads. No database/artifact is dropped, even after failure. It requires native test dependencies and is not a production recovery command. Tiny-fixture duration is not a production RTO/PITR demonstration.

## Health, logs, metrics and incidents

Backend liveness `/api/v1/health/live/` is process-only. Readiness `/api/v1/health/ready/` checks DB/migrations and production dependency policy. Both return status/service only, no-store; Host validation applies. Frontend `/health` checks itself. No health check calls the AI provider, and no separate worker exists. Operator-only `python manage.py operational_status` prints configuration-only AI status, storage/scanner flags, DB role policy, jobs by mode/state and oldest waiting age; provider reachability is explicitly not checked. Restrict shell access.

JSON logs include bounded correlation IDs, normalized route templates, method/status/duration, dependency/429 categories and committed audit action/outcome for jobs/review/application/assessment/security events. Unknown paths, queries, passwords, headers/cookies, source text, provider bodies and exception strings are suppressed; provider wire logging is disabled. Platform/ingress access logs must follow the same privacy policy. IDs are correlation labels, not authority. Restrict access/retention and document incident ownership, escalation and agreed tenant notifications.

Derive error/latency/429/readiness metrics from logs; poll operator status for state/age. Detailed attempt/failure categories, duration and candidate counts remain in authorized job/review records for a future controlled exporter. There is no public metrics endpoint, achieved SLO, load benchmark or broad telemetry stack. Establish baseline alerts for sustained 5xx/readiness, stale leases, scanner/limiter failures, capacity and backup/restore failures before launch.

## CI and synthetic extraction evaluation

CI covers locked Python/Node installs, pip consistency, PostgreSQL 17 tests, migration drift/apply/check, format/lint/typecheck, frontend tests/build, OpenAPI, core+SDK image builds/non-root/env/private-file checks and real Compose workflows. Script formatting explicitly uses `backend/pyproject.toml`. SDK transport is mocked; CI requires no API key. `check_ai_provider` without a flag is inert. Recovery drill is separate operator work, not ordinary CI.

Hosted status comes from GitHub for the actual SHA; YAML/local checks are not a hosted pass. After independently authorized commit/push, inspect `gh run list --repo user1738mike/physical-product-intelligence --workflow ci.yml --branch main` and `gh run view <run_id> --repo user1738mike/physical-product-intelligence --log-failed`. Inspect Actions annotations if no jobs started. Manual workflow_dispatch runs committed changes only; it does not test this uncommitted workspace. Do not push merely to trigger CI.

`python manage.py evaluate_extraction --output <new_result_path>` runs 18 synthetic schema/grounding/normalization/conflict cases with no provider calls, recording dataset/evaluation/mock-model versions and expected-case matches. It measures validation boundaries, not live precision/recall. Literal grounding can accept unrelated/product-versus-package facts in a valid quote; semantic attribution still needs human review. Existing service tests cover provenance, correction, reported-only application and explicit canonical selection. Representative customer documents/privacy approval are required before quality claims; never automatically tune prompts/rules from unreviewed evaluation.

## Optional live provider validation — explicit approval required

AI defaults off; missing key/model/SDK returns unavailable while deterministic/manual workflows work. Reuse existing server-side `OPENAI_API_KEY`; never create/reveal/copy/commit it or pass it to build/frontend. Set an approved Responses strict-JSON-Schema model in `AI_EXTRACTION_MODEL`, install optional SDK and enable AI in the operator process only after privacy review.

Only after explicit human authorization run `python manage.py check_ai_provider --allow-live-provider`. It makes one request through the existing adapter to fixed OpenAI origin with synthetic text “Synthetic carton specification. Weight: 1200 g. Length: 10 cm.”, `store=false`, 8-second timeout, no retry, ≤400 output tokens. It creates no DB records and reports sanitized category/model/elapsed/schema-grounding/1.2 kg validation status. It establishes neither quality nor throughput. Flag presence is not independent permission to make a paid request. Never run flagged command in CI/startup/ordinary tests. Phase 7 made no live call.

## Pre-release acceptance gates

- [ ] Approve reviewed commit/push separately; require passing hosted CI for exact SHA and resolve Actions failures.
- [ ] Build, scan and pin immutable images; validate actual secret injection and disabled-AI defaults.
- [ ] Verify TLS database CA/hostname, separate roles/grants, provenance/immutability triggers under runtime identity.
- [ ] Verify Host/origin/proxy spoof denial and session/CSRF/logout/role/tenant behavior through real TLS ingress.
- [ ] Provision encrypted persistent storage and current private scanner; test clean/infected/unavailable uploads and private/cross-tenant downloads.
- [ ] Approve retention/legal holds, incident ownership and monitoring; verify representative encrypted backup/PITR/isolated restore.
- [ ] Review schema compatibility, quiesce/back up, migrate once, check current migrations, roll out and probe external readiness.
- [ ] Test normal restart/persistence, DB/limiter failure and representative synchronous capacity; schedule queue follow-up if evidence requires it.
- [ ] Optionally authorize the single synthetic live check separately; review representative documents before AI quality claims.
- [ ] Record prior compatible image/forward-fix/isolated-restore rollback plan; obtain deployment approval. No destructive automatic rollback.
