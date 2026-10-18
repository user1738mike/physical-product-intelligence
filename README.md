
# physical-product-intelligence
Multi-tenant SaaS platform that builds evidence-backed digital profiles of physical products and evaluates their compatibility with handling, inspection, packaging, and automation workflows.
# Physical Product Intelligence Cloud

Current v1 completion work is tracked in [completion plan](docs/completion-plan.md),
[resumption state](docs/completion-state.md) and [acceptance status](docs/final-acceptance-report.md).
The phase descriptions below are historical; later reports identify implemented
commercial, billing and customer integration boundaries. Automatic maintenance
uses the [processor service](docs/processor-operations.md). Customer password
changes and operator-assisted recovery are described in [account recovery](docs/account-recovery.md).

A foundation for a multi-tenant product and packaging assessment platform, initially intended for warehouse robotics integrators. Phase 1 provides operational endpoints and a public identification page; Phase 2 adds session authentication, organizations, memberships, tenant authorization and audit history. Phase 3 adds structured product records, immutable packaging revisions, measurements and evidence provenance through tenant-scoped APIs. Phase 4 adds private CSV/XLSX uploads, bounded labeled PDF/TXT extraction, review candidates and transactional catalog application. Phase 5 adds equipment specifications, immutable rule versions and explainable recorded-input compatibility assessments. Architecture and requirements are in [docs](docs/product-requirements.md).

## Local development (PowerShell, repository root)

Prerequisites: running Docker Desktop with Linux containers and Compose v2, plus Python 3.13 for the standard-library setup script. Host Node 24 is optional for checks outside containers. No database port is exposed to the host.

```powershell
python scripts/setup_env.py
if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed' }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed; check required variables in .env' }
docker compose up --build -d db backend
if ($LASTEXITCODE -ne 0) { throw 'Database/backend startup failed; inspect Docker and service logs' }
docker compose exec -T backend python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Migrations failed; do not start frontend' }
docker compose exec -T backend python manage.py migrate --check
docker compose up --build --wait --wait-timeout 240
if ($LASTEXITCODE -ne 0) { throw 'Compose readiness failed; inspect Docker and service logs' }
python scripts/smoke.py
```

The setup script creates `.env` from `.env.example` only when `.env` is absent, generating a cryptographically secure Django secret key and PostgreSQL password with Python's `secrets` module. It never prints credentials and preserves an existing `.env` byte for byte, including on reruns. If using the existing virtual environment, replace `python` with `.\.venv\Scripts\python.exe`. Local credentials are not suitable for production; use the production secret manager procedure instead.

If an existing `.env` is incomplete or still contains placeholders, edit it explicitly; rerunning setup deliberately does not repair or rotate existing credentials. Keep the database and backend on the same `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` values; changing these does not update an initialized database volume. Stop if `config --quiet` fails. Compose's required-variable errors name the missing setting; shell environment variables take precedence over `.env`. Use `config --quiet` because plain `config` displays resolved secrets. `.env` is ignored by Git; `.env.example` remains tracked.

Compose consumes `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in both `db` and `backend`; `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS` are backend-only. The backend's database host/port and development settings module are fixed in Compose. Frontend `API_BACKEND_ORIGIN=http://backend:8000` is server-only and fixed in Compose; host frontend defaults to `http://127.0.0.1:8000`. No public frontend credentials are used.

Verify the setup logic with `python -m unittest discover -s scripts -p test_setup_env.py`.

Open http://localhost:3000. Backend liveness is http://localhost:8000/api/v1/health/live/, readiness is http://localhost:8000/api/v1/health/ready/, OpenAPI is http://localhost:8000/api/v1/schema/, frontend health is http://localhost:3000/health. Readiness includes database connectivity and pending migrations, plus production dependency policy when production settings are selected. Use `docker compose logs -f backend frontend` to inspect logs. Backend source is mounted with reload; frontend source is baked into its development image: after edits run `docker compose up -d --build frontend`. This avoids host/container node_modules conflicts.

```powershell
docker compose exec -T backend ruff format --check .
docker compose exec -T backend ruff check .
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test accounts organizations operations products ingestion compatibility --settings=config.settings.test
docker compose exec -T backend python manage.py spectacular --validate --fail-on-warn --file /tmp/openapi.yaml
docker compose exec -T frontend npm run format:check
docker compose exec -T frontend npm run lint
docker compose exec -T frontend npm run typecheck
docker compose exec -T frontend npm test
docker compose exec -T frontend npm run build
docker build --target production -t ppi-frontend ./frontend
docker compose down
```

`down` preserves development data. `docker compose down --volumes` permanently deletes this project's development database; use it only for an intentional reset. Changing POSTGRES values does not change credentials inside an already initialized volume.

## Optional host checks

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock
.\.venv\Scripts\ruff.exe format --check backend scripts
.\.venv\Scripts\ruff.exe check backend scripts
$env:DJANGO_SETTINGS_MODULE = 'config.settings.test'
$env:TEST_SQLITE = '1'
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py test accounts organizations operations products ingestion compatibility
.\.venv\Scripts\python.exe backend\manage.py spectacular --validate --fail-on-warn --file artifacts\openapi.yaml
Remove-Item Env:TEST_SQLITE
Remove-Item Env:DJANGO_SETTINGS_MODULE
Set-Location frontend
npm.cmd ci
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
Copy-Item -LiteralPath .next\static -Destination .next\standalone\.next\static -Recurse -Force
$env:HOSTNAME = '127.0.0.1'
$env:PORT = '3000'
npm.cmd start
```

Create `artifacts` before exporting the schema (`New-Item -ItemType Directory -Force artifacts`). SQLite host checks are smoke tests only; PostgreSQL integration verification is mandatory in Compose/CI. Host Django does not auto-load `.env`; configure POSTGRES variables explicitly if connecting to a separately provisioned local database. The Compose database intentionally has no host port. On POSIX use `cp`, `export`, `.venv/bin/python` and `npm` equivalents.

## Dependencies and CI

`backend/requirements.lock` pins the complete Python environment; `requirements.in` documents upgrade inputs. Update in a clean Python 3.13 environment, run `pip install -r requirements.in`, then `pip freeze --local` into the lock and review the diff. Frontend direct versions are exact and `npm ci` consumes package-lock.json. Docker images use version tags; production release promotion requires verified digest pins and scans. CI runs checks against PostgreSQL and a Compose smoke job. A configured workflow is not evidence that a hosted CI run passed.

## Operations and next phase

See [architecture](docs/system-architecture.md), [domain model](docs/domain-model.md), [threat model](docs/security-threat-model.md), [test strategy](docs/testing-strategy.md), [operations](docs/deployment-and-operations.md) and [ADRs](docs/architecture-decisions). Production settings require explicit secrets and safe host/origin configuration; the development Compose file is not a production deployment. No private files are served and no S3/Celery integrations are claimed.

## Accounts and organizations

The signed-in workspace now has a shared organization dashboard at
`/organizations/{organizationId}/dashboard`. Organization selection opens
Overview; a single-membership sign-in lands there directly. The sidebar connects
products, imports/review, equipment/rules, assessments, plan/usage, billing,
integrations and settings while preserving nested direct URLs. Account and
recovery remain separate and reachable from the header. Members see their
permitted sections; management actions retain existing server authorization.
See the [dashboard walkthrough](docs/dashboard-walkthrough.md) for navigation,
real-data summaries, API mapping and actual verification results.

After applying migrations, open http://localhost:3000/account to register, sign in, create an organization and select your organization context. Registration uses a case-sensitive username (ASCII letters, digits, dot, underscore and hyphen) and a validated password of at least 12 characters. It never creates staff or superusers. Django's existing `auth.User` is retained to preserve migration history; email identity, email verification, recovery, invitations, MFA and SSO are deferred. An authorized owner/admin may add an already registered user by username through the membership API; no email delivery is claimed.

Existing Django usernames, including Unicode and `@`/`+`, remain valid at login; the registration character policy applies only to new accounts. A newly created organization is added to the selector using its server-returned membership even when it falls beyond the first page. Later pages update roles without duplicating organizations.

Sessions use HttpOnly cookies, SameSite=Lax, an eight-hour absolute expiry and browser-close expiry; production also requires Secure cookies and TLS. The frontend fetches a fresh CSRF token for every mutation, including login/registration, and keeps no authentication secrets in localStorage. Production must route `/api/v1/` directly to Django under the same TLS origin, with explicit HTTPS CSRF trusted origins; no permissive CORS is installed. If using the standalone frontend proxy instead, set `API_BACKEND_ORIGIN` in the server runtime environment and verify its Origin behavior in staging. Development trusts only localhost/127.0.0.1 frontend origins on port 3000.

The server-only `/api/v1/[...path]` route forwards requests with Node fetch to the configured backend, replacing the rewrite proxy that produced intermittent `ECONNRESET` failures. It preserves Django trailing slashes, session/CSRF cookies and Origin, limits request bodies to 64 KiB, sets a 30-second upstream timeout, and returns non-cacheable responses. Transport failures return a generic 502 without logging credentials or automatically replaying requests. No global HTTP-agent preload is required. The live smoke test defaults to 200 consecutive CSRF/profile reads and also checks missing CSRF, hostile origins, cookie attributes, roles, revocation and logout replay denial. Run it only against a disposable database.

The production Dockerfile packages `.next/static` alongside the standalone server. For a native standalone run, copy `frontend/.next/static` into `frontend/.next/standalone/.next/static` after each build before `npm run start`; otherwise generated stylesheet URLs return 404.

| Action | Owner | Admin | Member |
| --- | --- | --- | --- |
| View organization and members | Yes | Yes | Yes |
| Rename organization / add or remove ordinary members | Yes | Yes | No |
| Add/remove admins / change non-owner roles | Yes | No | No |
| Transfer ownership / suspend or reactivate | Yes | No | No |
| Read organization audit events | Yes | Yes | No |

The owner cannot be removed or demoted; transfer atomically promotes an existing active member and makes the former owner an admin. A database constraint permits at most one owner; service transactions preserve an owner on every supported operation. Suspended tenants deny protected operations; only their owner may reactivate them. Staff privileges provide no tenant API bypass. Administrators cannot edit owner/admin privileges. Slugs are immutable, and hard organization deletion is unavailable. If an owner account is deactivated, an authorized operator must restore that account before transferring ownership; there is no automatic takeover.

API contract is available at `/api/v1/schema/`:

| Endpoint | Method / behavior |
| --- | --- |
| `/api/v1/auth/csrf/` | GET masked CSRF token; session cookie is never exposed |
| `/api/v1/auth/register/`, `/login/`, `/logout/` | POST account creation, login, logout (the latter paths share `/api/v1/auth/`) |
| `/api/v1/auth/me/`, `/api/v1/auth/memberships/` | GET current profile and paginated memberships |
| `/api/v1/organizations/` | POST `{name, slug}`; caller becomes owner |
| `/api/v1/organizations/{id}/` | GET; PATCH `{name}` |
| `/api/v1/organizations/{id}/members/` | GET; POST `{username, role}` (`member` default; `admin` owner-only) |
| `/api/v1/organizations/{id}/members/{membership_id}/` | GET; PATCH `{role}` owner-only; DELETE authorized removal |
| `/api/v1/organizations/{id}/transfer/` | POST `{membership_id}` owner-only |
| `/api/v1/organizations/{id}/state/` | POST `{is_active}` owner-only |
| `/api/v1/organizations/{id}/audit/` | GET paginated read-only history |

Collections have 25-item pages with `count`, `next`, `previous`, `results`. Inaccessible tenants/nested objects return 404; role/session denials return 403; duplicate organization slugs return 409. Unknown or ownership/organization fields are rejected. All unsafe requests need the token from `auth/csrf/` in `X-CSRFToken`, plus the cookies. Auth errors are generic. Login is limited to 10/minute and registration to 5/hour per trusted peer using shared PostgreSQL counters; ingress abuse protection is also required. Account responses omit password hashes, email and privilege flags.

For trusted operator administration, run `docker compose exec backend python manage.py createsuperuser` interactively and visit http://localhost:8000/admin/. Tenant/audit admin pages are read-only; use the authorized APIs to mutate tenant state. Never grant staff privileges through public registration. Restrict `/admin/` at production ingress and collect/serve its static assets separately.

Optional live authentication smoke (creates disposable accounts/organizations; run only against a disposable test database):

```powershell
python scripts/phase2_smoke.py --allow-create-test-data
```

The backend tests include CSRF-enforced clients, session revocation, tenant/nested denials, role constraints, transaction rollback, audit preservation, provenance/measurement validation and PostgreSQL concurrent ownership/revision/edit tests. SQLite cannot prove row locks or PostgreSQL provenance guards. See [Phase 2 report](docs/phase2-implementation-report.md), [Phase 3 completion report](docs/phase3-completion-report.md) and [roadmap](docs/engineering/phase-roadmap.md) for actual acceptance results and runtime blockers.

## Product and packaging APIs

Phase 8 adds an isolated HTTPS deployment rehearsal, real ClamAV failure checks, controlled migration/backup/restore/rollback tooling and immutable local artifact evidence. Start with the [deployment plan](docs/phase8-deployment-plan.md), [release checklist](docs/phase8-release-checklist.md) and [actual results/blockers](docs/phase8-completion-report.md). A local rehearsal is not staging or production acceptance. Phase 8 makes no live AI calls; commercial billing/entitlements remain unimplemented.

Phase 3 includes the product-management workspace at `/products`: choose an organization, search/page its catalog, create and edit products, manage named packaging profiles, record attribute claims, review conflicts and read history. Owners/admins can record documented physical measurements, select a claim with rationale, and archive/reactivate products or packaging. Members can contribute reported/estimated claims and catalog data. Open it from Account or the landing page. Start with the [API guide and request examples](docs/product-api.md) and [completion report](docs/phase3-completion-report.md). All API routes remain under `/api/v1/organizations/{organization_id}/products/`, protected by current membership and session/CSRF. Staff has no implicit tenant access. Archival retains history and stops writes; suspended tenants deny product access.

Products have tenant-unique, case-sensitive immutable SKUs. Creation writes revision 1 atomically; subsequent writes append complete immutable snapshots with sequential revision numbers. Packaging supports unit/inner/case/pallet containment. Measurements preserve original decimals, exact metric normalization, optional uncertainty bounds, observation method/time and required evidence references. Missing measurements remain unknown and conflicting observations remain separate.

Evidence records retain attribution, declared license, source reference, observed/recorded times and recording user. `capture_status=reference_only` and `declared_sha256` describe unverified artifact metadata: no files are uploaded/fetched/inspected. Attribute claims distinguish reported, estimated and physically verified (attested) observations. A verification creates a new measured claim with instrument, procedure, source, actor and time; it preserves the original estimate. Only an owner/admin selection with rationale supplies a canonical attribute value. New conflicting claims reopen the decision. Mutable URLs alone are not reproducible captured artifacts. Correct records by adding new evidence/revisions; hard deletion and historical edits remain unavailable. See ADR 0008 for database guards and verification limits.

On a disposable database only, run `python scripts/phase3_smoke.py --allow-create-test-data` to verify the full workflow through Next.js. It creates and retains fixture accounts, tenants, products and evidence; never run it on customer data. CI runs both Phase 2 and Phase 3 smoke checks.

Historical Phase 1 execution results remain in `docs/implementation-report.md`.

## Evidence imports

Choose an organization in the product workspace, then open Imports. Upload, validate, confirm mappings, review candidates and approve creation before applying. Only owners/admins approve or apply; imported measurements remain reported evidence. See [ingestion API and setup](docs/ingestion-api.md), [ADR 0009](docs/architecture-decisions/0009-bounded-reviewable-ingestion.md) and the [Phase 4 completion report](docs/phase4-completion-report.md). Production uploads require a malware scanner and private storage configuration.

## Equipment and compatibility assessments

From an organization workspace, open Equipment to record specifications, create immutable rule versions and activate reviewed constraints. All members can use Assessments to select a product/package, equipment, explicit orientation and eligible rule version, then inspect evidence sufficiency, per-rule results and immutable history. Missing critical values remain indeterminate; estimates never become verified facts. These results do not certify physical safety or successful handling. See the [API and lifecycle guide](docs/compatibility-api.md), [ADR 0010](docs/architecture-decisions/0010-versioned-equipment-and-deterministic-assessments.md) and [Phase 5 report](docs/phase5-completion-report.md). The full backend command includes `accounts organizations operations products ingestion compatibility`; the existing disposable Phase 3 smoke now also covers Phase 4 and Phase 5.

## AI-assisted evidence extraction

Phase 6 extends existing imports with optional source-grounded AI candidates, explicit review/correction and atomic application. Open an original upload to check availability, select an existing product/package and queue a job. Processing requires a separate action that sends bounded source text to the configured provider. AI is disabled by default, credentials remain backend-only, and deterministic parsing/manual review remain available. Optional SDK setup, privacy controls, limits and API examples are in the [AI guide](docs/ai-extraction-api.md), [ADR 0011](docs/architecture-decisions/0011-source-grounded-ai-candidates.md) and [completion report](docs/phase6-completion-report.md). Automated tests and CI use mocked responses; a live integration check requires separate authorization.

## Phase 7 operational hardening

Shared PostgreSQL admission limits, a global extraction cap, migration/role-aware readiness, private scanner hook, protected backup/isolated restore commands and production server/image recipes are implemented. Use the [operations guide](docs/deployment-and-operations.md) for safe startup order, project-only Docker subnet recovery, TLS/role/storage requirements, recovery and release gates. Local production-server verification uses `compose.runtime-check.yaml`; production configuration uses the separate `compose.production.yaml` recipe. See [ADR 0012](docs/architecture-decisions/0012-small-deployment-operational-controls.md) and the [Phase 7 verification report](docs/phase7-completion-report.md). Live OpenAI calls require separate explicit approval; ordinary checks use mocks and an 18-case synthetic validation evaluation.
