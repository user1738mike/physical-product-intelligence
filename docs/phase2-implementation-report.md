# Phase 2 implementation and acceptance report

Date: 2026-10-14, Africa/Nairobi. Branch: `main`, baseline commit `a02408a`. Phase 1 environment changes were already uncommitted when this task began and were preserved. No commit, staging or push was performed. Phase 3 has not started.

## Implementation

Accounts use existing Django `auth.User`, case-sensitive username login, validated Django password hashing, registration without privilege fields, login/logout/current profile and paginated current memberships. No custom-user switch or auth migration rewrite occurred. Admin integration uses Django's existing UserAdmin; tenant/audit admin pages are read-only. Sessions have HttpOnly/SameSite=Lax cookies, eight-hour absolute expiry, browser-close expiry and production Secure/TLS. Anonymous login/registration explicitly enforce CSRF; every browser mutation obtains a fresh masked token. Account/tenant responses are non-cacheable. Public registration does not auto-login; the browser then performs the separate protected login step. Login and registration have DRF scoped throttles.

Organizations have UUIDs, unique immutable slugs, names, lifecycle state and timestamps. Memberships have UUIDs, user/organization foreign keys, owner/admin/member roles, unique organization/user pairs, a role check and a partial unique owner constraint. The caller becomes initial owner transactionally; duplicate slugs cannot leave partial memberships. Services lock organization writes, recheck current active membership/role, scope nested lookups, preserve a sole owner, and transfer ownership transactionally. Administrators cannot manage administrative privileges; suspended tenants block resources except owner reactivation. Staff has no implicit tenant API bypass. No bulk or product endpoints exist. See the role matrix in README and ADR 0006.

Audit events record IDs/time, nullable actor/tenant, fixed action/target/outcome fields and allowlisted role metadata. Success events commit with business actions; selected API authorization failures and failed login are separate failure records. No passwords/cookies/tokens/headers/submitted usernames are recorded. No audit mutation API exists; ORM/admin guards supplement access control. Organization audit references protect deletion; actor deletion preserves the event with a null actor. DB operators remain trusted: no RLS or database-level immutable audit enforcement is claimed. A live check found Django's inherited server handler bypassed the Phase 1 formatter; explicit Django logger configuration now uses the existing redaction formatter, with a configured-handler regression test.

The account frontend includes registration/sign-in, loading/error/anonymous/authenticated state, sign-out, paginated organization selection and organization creation. Typed API functions cover all implemented endpoints. Forms have labels/autocomplete, keyboard focus styles, live status and feedback focus. It stores no authentication secrets in localStorage. The server-only API route uses the Docker service name in Compose and loopback on the host, configured at runtime. API trailing slashes are explicitly preserved; the real proxy smoke exercises that contract. Product UI remains unavailable.

## Models, migrations and API

Additive migrations: `organizations/0001_initial` creates Organization/Membership and constraints; `audit/0001_initial` creates AuditEvent and the tenant/time index. Enabling standard Django admin also applies its three existing framework migrations. Prior isolated PostgreSQL history contained all 12 auth migrations, two contenttypes migrations and sessions; inspection found zero users before migration. All existing migration records and tables were retained.

Authentication endpoints under `/api/v1/auth/`: `csrf/` GET, `register/` POST, `login/` POST, `logout/` POST, `me/` GET, `memberships/` GET. Tenant endpoints: `/api/v1/organizations/` POST; `{id}/` GET/PATCH; `{id}/members/` GET/POST; `{id}/members/{membership_id}/` GET/PATCH/DELETE; `{id}/transfer/` POST; `{id}/state/` POST; `{id}/audit/` GET. Collections return 25-item page envelopes. OpenAPI includes strict request shapes and explicit paginated response schemas. Inaccessible resources use 404, role/session denial 403, duplicate organization slugs 409. Ownership/organization/privilege payload manipulation is rejected.

## Executed verification

Commands ran in PowerShell from the repository root unless marked `frontend`. Installed runtimes required approved access outside sandbox restrictions. Native PostgreSQL is 16.13, not the Compose PostgreSQL 17.11 image. Host test DB credentials are isolated fixtures, not local `.env` or production secrets.

| Command / check | Actual result |
| --- | --- |
| `git status --short`, branch/log, repository/security/settings/test inspection | `main`, `a02408a`; preserved six pre-existing Phase 1 changed/new files |
| `backend/manage.py showmigrations` plus read-only PostgreSQL migration/user counts | Existing default-user migration graph confirmed; prior isolated cluster had 15 applied framework migrations and zero users |
| `pg_ctl -D artifacts/postgres16-test ... -h 127.0.0.1 -p 55432 -w start` | Started only the previously documented isolated test cluster |
| With `DJANGO_SETTINGS_MODULE=config.settings.test`, `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=55432`, `POSTGRES_USER=ppi`, `POSTGRES_DB=ppi`: `.\.venv\Scripts\python.exe backend/manage.py migrate --noinput` | All additive tenant/audit and standard admin migrations applied successfully |
| Same environment: `.\.venv\Scripts\python.exe backend/manage.py test accounts organizations operations --keepdb --verbosity 0` | 34 tests passed on PostgreSQL; concurrent ownership test executed, not skipped |
| `ruff.exe format --check backend scripts`, `ruff.exe check backend scripts` | Passed for 38 Python files |
| `backend/manage.py check`, `makemigrations --check --dry-run`, `migrate --check` | Passed; no migration drift or unapplied migrations |
| `backend/manage.py spectacular --validate --fail-on-warn --file artifacts/openapi-phase2.yaml` | Passed without warnings/errors |
| `python -m unittest discover -s scripts -p test_setup_env.py` | All four Phase 1 setup regression tests passed |
| `python -m pip check` | No broken requirements; dependencies unchanged |
| `frontend`: `npm.cmd audit --audit-level=high` | Zero reported vulnerabilities; no dependency changes |
| `frontend`: `npm.cmd run format:check`, `lint`, `typecheck`, `test` | Passed; six frontend tests |
| `frontend`: `npm.cmd run build` | Standalone build passed, including account route and TypeScript |
| Production `backend/manage.py check --deploy` with synthetic secrets/explicit HTTPS origins | No errors; existing W005/W021 HSTS subdomain/preload warnings retained, no warnings silenced |
| `docker compose config --quiet` | Passed without exposing resolved secrets |
| `docker compose up --build -d` | Application images built; startup blocked by `all predefined address pools have been fully subnetted` |
| `docker compose build` after final proxy/logging corrections | Both final application images built successfully; normal container runtime remains blocked |
| `docker compose ps -a` | No project containers running; container migrations/tests/health remain incomplete |
| Native hidden Django development server (loopback 8000, disposable `test_ppi`) and built standalone frontend (loopback 3000) | Used only for HTTP verification; results below |
| `python scripts/smoke.py` | Backend liveness, real PostgreSQL readiness, frontend health, landing disclosure and CSS all passed |
| `python scripts/phase2_smoke.py --allow-create-test-data` through the final standalone frontend | Passed real registration, login, profile, initial owner creation, cross-tenant/nested denial, scoped audit access and logout; exit zero |
| Live Django request with a non-secret query fixture, private log scan | Query value absent from configured request/server logs |
| Private local-credential scan over tracked/new source, `git check-ignore .env`, `git ls-files .env`, staged-name check, `git diff --check` | No local credential disclosure in source; `.env` ignored/untracked/unstaged, nothing staged, whitespace check passed |

The first root-level `manage.py test` discovered zero tests; subsequent runs explicitly selected the three modules, and CI/README now do likewise. Initial serializer error shaping and schema enum/page naming failed and were corrected without silencing checks. PostgreSQL tests initially passed assertions but cleanup failed because worker connections remained open; worker `connections.close_all()` fixed this and the final run exited zero. An early native smoke raced frontend startup; readiness was awaited before rerunning. Real proxy checks exposed Next.js 308 slash-removal and Django 301 slash-append redirects; disabling Next's automatic slash redirect and explicitly ending the rewrite destination with a slash fixed both. The final real proxy smoke, including credentials and mutations, passed. A rebuild while the standalone frontend ran failed with Windows EBUSY; only the verified temporary process was stopped before the successful rebuild.

## CI and limitations

CI's PostgreSQL backend job explicitly runs accounts/organizations/operations tests, migration drift and schema checks. The frontend job runs lint/typecheck/tests/build. Compose smoke additionally exercises registration/login/tenant denial/audit/logout through Next.js using `scripts/phase2_smoke.py --allow-create-test-data`. CI creates only disposable fixture data; no hosted run was executed or claimed.

Deferred: email identity/verification/delivery/invitations, recovery, MFA/SSO, member administration screens, distributed abuse limits, audit archival/purge/immutable sink and production ingress/TLS staging verification. Public registration uses usernames; it does not verify inbox ownership. Authorized owner/admin member provisioning targets already registered active accounts. Audit retention is provisionally 365 days pending review; no purge is implemented. No customer deployment, penetration test or production readiness certification is claimed. Docker pool exhaustion remains an external blocker; no networks or volumes were pruned/deleted.

## Changed files and start/test commands

Phase 2 additions: `backend/accounts/{__init__,serializers,views,tests}.py`; `backend/organizations/{__init__,models,admin,serializers,services,views,tests}.py` and `migrations/{__init__,0001_initial}.py`; `backend/audit/{__init__,models,admin,services}.py` and `migrations/{__init__,0001_initial}.py`; `frontend/app/account/{page,account}.tsx`, `frontend/lib/api.ts`, `frontend/tests/api.test.tsx`, `scripts/phase2_smoke.py`, ADR 0006, this report and `docs/engineering/phase-roadmap.md`.

Phase 2 edits: backend base/development settings, routing, existing log formatter/test; Compose's server-only frontend destination; frontend navigation/styles/proxy config; CI; README; existing architecture, domain, threat, testing and tenant ADR documents. Pre-existing `.env.example`, environment setup scripts and historical implementation report remain preserved. Local `.env` was not modified; no generated credential was committed, staged or printed.

After resolving Docker network allocation, from repository root:

```powershell
python scripts/setup_env.py
if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed' }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed' }
docker compose up --build --wait --wait-timeout 240
if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed' }
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T backend python manage.py test accounts organizations operations --settings=config.settings.test
docker compose exec -T backend python manage.py spectacular --validate --fail-on-warn --file /tmp/openapi.yaml
docker compose exec -T frontend npm run format:check
docker compose exec -T frontend npm run lint
docker compose exec -T frontend npm run typecheck
docker compose exec -T frontend npm test
python scripts/smoke.py
```

Visit http://localhost:3000/account. Run `python scripts/phase2_smoke.py --allow-create-test-data` only when the running stack has a disposable database; it intentionally creates test accounts/tenants and does not delete them. Never run it on customer/production data. Existing migrations are additive; production still requires a verified backup and reviewed release migration step. Host SQLite smoke commands are in README and do not prove row-lock behavior.

## Acceptance

- [x] Authentication/session/CSRF flows implemented and backend-tested.
- [x] Additive organization, membership and audit migrations applied to isolated PostgreSQL.
- [x] Roles, tenant scoping, revocation, suspension and single-owner/transfer protections tested.
- [x] Audit secrecy, immutability, actor retention and transactional rollback tested.
- [x] Cross-tenant read/write/nested denial and actual persisted invariants tested.
- [x] Backend/frontend checks, schema validation and production configuration review passed with documented warnings.
- [x] CI configuration and architecture/security/API documentation updated.
- [x] Real frontend authentication proxy and Phase 1 health/landing smoke passed on the native disposable PostgreSQL database.
- [ ] Docker PostgreSQL 17.11 container runtime and hosted CI verified (external runtime blocker / hosted CI not run).
- [ ] Production TLS/ingress/abuse protection/retention and full interactive accessibility release verification.

Temporary application listener PIDs were checked against their exact Python runserver/standalone Node command lines before being stopped. The previously stopped isolated PostgreSQL cluster was returned to stopped state with `pg_ctl -D artifacts/postgres16-test -m fast -w stop`. Its databases and ignored test/build/log artifacts were preserved. No unrelated listeners, Docker networks, volumes or customer data were changed. Final Git status contains the reviewed modified Phase 2 files/new modules plus preserved pre-existing Phase 1 changes; `.env` is absent from tracked/staged files and no commit/push occurred.

Phase 2 implementation is ready for review; full runtime/deployment acceptance remains subject to the explicitly incomplete checks above.

## Final security verification — 2026-10-14

The working tree already contained the replacement transport at `frontend/app/api/v1/[...path]/route.ts`. Prior local rewrite logs contained `read ECONNRESET`; the replacement uses Node fetch rather than Next's rewrite proxy. It forwards only allowlisted request/response headers, preserves separate Set-Cookie headers, removes decompression-sensitive response headers, preserves trailing slashes, bounds request bodies to 64 KiB, uses a 30-second timeout and returns generic non-cacheable 502 errors. Requests are never automatically replayed. The six transport tests verify credential/header forwarding, both cookies, bodyless logout, request-size rejection, traversal denial and safe failure without mutation replay. No global agent override or preload is part of the current implementation. README and architecture documentation were corrected accordingly; the earlier rewrite description above records the historical implementation.

Added explicit backend regression checks for login CSRF-secret rotation, rejection of pre-login tokens, successful fresh-token mutation and Secure session/CSRF cookies over HTTPS settings. Expanded `scripts/phase2_smoke.py` to check missing CSRF and hostile origins, non-cacheable responses, HttpOnly/SameSite/browser-close session attributes, ordinary-member denial, allowed admin rename, forbidden admin privilege/state changes, membership revocation and session-cookie replay denial after logout. Its bodyless DELETE request now obtains CSRF, as required by Django.

| Final check | Executed result |
| --- | --- |
| PostgreSQL 16.13: `manage.py test accounts organizations operations --keepdb --verbosity 0` | **37 passed**, including the concurrent transfer test; exit zero. Log: ignored `artifacts/phase2-final-tests.log`. |
| Existing isolated PostgreSQL `ppi`: `migrate --noinput`, `migrate --check`, `makemigrations --check --dry-run`, `check` | Passed; no pending migrations or model drift. |
| `spectacular --validate --fail-on-warn` | Passed; ignored `artifacts/openapi-phase2-final.yaml`. |
| Dedicated new database `ppi_phase2_verification` on loopback 55432 | All 20 framework/application migrations applied successfully. No customer database or local `.env` was used. |
| Frontend `npm test`, `lint`, `typecheck`, `format:check` | **15 tests passed** across four files; all checks passed. |
| Frontend `npm run build` | Production standalone build passed with the dynamic API route. |
| Built standalone frontend on port 3000 → dedicated Django development server on port 8001 | Expanded live smoke **passed**, including **200 consecutive CSRF/profile reads with zero resets**, registration/login, CSRF/origin rejection, cookie attributes, tenant/role denial, admin permissions, revocation, audit, logout and session replay denial. This is bounded verification, not a guarantee against all future transport failures. |
| Health and landing smoke | Passed. The native standalone copy initially lacked current static assets; copied `.next/static` into standalone `.next/static` and restarted the verification frontend before the passing run. Dockerfile already packages those assets. Dedicated port-8001 database readiness also passed. |
| Environment setup regressions | **4 passed** outside the restricted sandbox after temporary-file permission failures inside it. |
| Ruff lint/format, pip dependency consistency, whitespace check | Passed. |
| Production `check --deploy` using synthetic fixture configuration | Only the existing W005/W021 HSTS subdomain/preload warnings; no errors. No real TLS ingress was exercised. |
| `docker compose up --build -d` | Both application images rebuilt successfully; network creation still fails with `all predefined address pools have been fully subnetted`. Container runtime remains unverified. No network/volume pruning performed. |

The final run used PostgreSQL already running before this pass; it remains running. The pre-existing Django listener on port 8000 was used only for read-only health checks. Only this pass's dedicated port-8001 Django and port-3000 Node servers were stopped after verification, with PID/command-line validation. The dedicated disposable database and ignored logs/build artifacts are retained. No commits, staging, push, hosted CI run or deployment occurred.

All requested application security checks pass in the native PostgreSQL setup. Remaining environment/release gates are Docker runtime (host pool exhaustion), hosted CI execution and real production TLS/ingress verification. Phase 3 has not started.
