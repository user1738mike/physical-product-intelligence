# Phase 0 and Phase 1 implementation report

## Environment setup follow-up — 2026-10-14 (Africa/Nairobi)

The original missing-variable errors were caused by having no local `.env`; Compose does not load `.env.example` automatically. At this follow-up's initial inspection, `.env` already existed with all four required values, including template credential placeholders. It was ignored and untracked. Its contents were never printed and its SHA-256 comparison before/after setup confirmed byte-for-byte preservation.

Changed `.env.example` comments and README setup instructions, added `scripts/setup_env.py` and four focused tests in `scripts/test_setup_env.py`, and replaced CI's template copy with the same tested generator. Compose, backend settings, dependencies and `.gitignore` already had the required configuration and were preserved. This report records the follow-up results separately from the historical implementation below.

The setup script copies the example only when `.env` is absent, generates separate Django/PostgreSQL credentials with standard-library `secrets.token_hex(32)`, does not print them, and uses exclusive file creation to prevent overwriting a concurrent setup. Existing files are preserved even if incomplete; Compose retains required-variable validation. Non-secret development defaults remain `ppi` for database/user and loopback/backend allowed hosts. Both database and backend consume the same PostgreSQL variables. Production settings and their missing/unsafe-key rejection were unchanged and tested.

Commands and actual results (repository root unless specified):

| Commands/checks | Result |
| --- | --- |
| `git status --short`, source/settings/setup inspection | Initially clean; no existing setup generator; existing local `.env` found |
| `.\.venv\Scripts\python.exe -m unittest discover -s scripts -p test_setup_env.py` | Four tests passed: generation/no console disclosure, rerun preservation, invalid template, concurrent creation |
| `.\.venv\Scripts\python.exe scripts/setup_env.py` | Existing `.env` preserved; private before/after file-hash comparison passed |
| `.\.venv\Scripts\ruff.exe format --check backend scripts` and `ruff.exe check backend scripts` | Passed for all 18 files after formatting only the two new scripts; initial format check correctly identified those files |
| With `DJANGO_SETTINGS_MODULE=config.settings.test`, `TEST_SQLITE=1`: `.\.venv\Scripts\python.exe backend/manage.py check` | No issues |
| Same environment: `backend/manage.py makemigrations --check --dry-run` | No changes detected |
| Same environment: `backend/manage.py test operations` | Nine tests passed, including production missing-variable/unsafe-secret rejection; SQLite smoke coverage, not PostgreSQL integration |
| Same environment: `backend/manage.py spectacular --validate --fail-on-warn --file artifacts/openapi-env-check.yaml` | Passed |
| In `frontend`: `npm.cmd run format:check`, `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd test` | All passed; two frontend tests |
| `docker compose config --quiet` | Passed, using preserved local `.env`; quiet mode avoids disclosing resolved credentials |
| Generator exercised in ignored `artifacts/env-config-check`, then `docker compose --env-file artifacts/env-config-check/.env config --quiet` | Fresh generated environment passed; no generated credentials displayed |
| Private JSON capture from `docker compose --env-file artifacts/env-config-check/.env config --format json` | Verified database/backend credential references match; JSON was not printed or logged |
| `docker compose --env-file artifacts/env-config-check/empty.env config --quiet` with private output capture | Empty configuration correctly rejected with an actionable required-variable message |
| `docker compose up --build -d` | PostgreSQL image pulled and both application images built successfully. Startup failed: `all predefined address pools have been fully subnetted` |
| `docker compose ps`, `docker compose ps -a` | No project containers listed |
| `docker compose logs --no-color --tail 30` | No service logs available because startup failed before services ran |
| Read-only `docker network ls`, bridge IPAM inspection, `docker info --format '{{json .DefaultAddressPools}}'` | Docker has many existing bridge networks; bridge uses `172.17.0.0/16`; no custom default pools reported. No networks were removed or modified |
| `.\.venv\Scripts\python.exe scripts/smoke.py` | Failed at backend liveness with connection refused; no successful HTTP smoke claimed |
| Separate probes of backend liveness, database readiness and frontend health | All unreachable; live service verification remains incomplete |
| `git check-ignore .env .env.local .env.production backend/.env frontend/.env artifacts/env-config-check/.env` | Local environment files ignored; `.env.example` remains tracked |
| `git ls-files .env`, `git diff --cached --name-only` | No tracked/staged `.env`; nothing staged |
| `git diff --check` | Passed; Git emitted only existing LF/CRLF conversion notices |

Initial sandbox execution could not access the installed Python executable/Docker configuration and API. Approved execution allowed the checks above and confirmed Docker Desktop is available. An initial individual HTTP probe had a shell quoting error; the corrected probe ran against all three endpoints. No application checks were suppressed.

After the user explicitly authorized replacing only template credentials, a separate local operation replaced the exact placeholder assignments for `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` using `secrets.token_hex(32)`. Every other line, including line endings, was preserved byte for byte. Generated values were never displayed. `docker compose config --quiet` passed again; `.env` remains ignored, untracked and unstaged. The setup script itself continues to preserve existing files on reruns. No database credential alteration or volume reset was performed.

Remaining issues: Docker's host address pools are exhausted, preventing the normal Compose network from being created. Resolve host network allocation before rerunning README startup/migrations/PostgreSQL tests/smoke verification. Do not prune networks or delete volumes without reviewing other projects. Local credentials must never be used in production. No database migrations or container integration tests could run; no database/backend/frontend health check passed. Frontend-to-backend application calls do not exist in Phase 1; smoke checks probe the services independently.

Final source changes are `.env.example`, `.github/workflows/ci.yml`, `README.md`, this report, and the two new setup scripts. Only the authorized local template credentials were replaced; no existing developer secrets, database data, volumes or networks were deleted or overwritten. Ignored verification artifacts remain local. Phase 2 has not started. No commit, staging or push was performed.

Date: 2026-10-13 (Africa/Nairobi). Repository was empty except for `.git`; `master` had no commits. No existing source was overwritten. No commit or push was performed.

## Delivered

Architecture documents, five ADRs, Django/DRF operational API with OpenAPI, PostgreSQL configuration, environment-separated settings, exact Python dependency lock, Next.js TypeScript landing page, frontend health endpoint, npm lockfile, local Compose, non-root container images, backend/frontend tests, CI, smoke script and setup/operations instructions. Celery, Redis, S3, identity flows, tenant data and assessments are deliberately deferred until their workflows are implemented.

## Verification results

| Check | Result and limits |
| --- | --- |
| Ruff lint and formatting | Passed for backend and scripts (16 Python files) |
| Django system check | Passed |
| Migration drift | `makemigrations --check --dry-run`: no changes |
| Backend tests, SQLite | 8 passed; smoke verification only |
| Backend tests, native PostgreSQL 16.13 | 9 passed after final log-redaction regression test; isolated loopback test cluster, no existing databases used |
| PostgreSQL migrations | All framework migrations applied; `migrate --check` passed |
| OpenAPI | Validation and `--fail-on-warn` passed, including PostgreSQL-configured run |
| Python lock consistency | Installed pins satisfied; `pip check` passed. This was not a fresh Linux lock install |
| Production Django check | No errors; warnings W005 (HSTS subdomains) and W021 (preload). These are intentionally disabled pending domain control verification; no warnings silenced |
| Frontend formatting, lint, typecheck | Passed after correcting navigation and obsolete Vitest configuration |
| Frontend tests | 2 passed |
| Frontend production build | Passed with standalone output after rerunning with approved filesystem access |
| Clean npm lock install and audit | `npm ci` passed; final audit reported zero vulnerabilities |
| Live HTTP smoke | Backend liveness and PostgreSQL readiness, frontend health, landing disclosure and CSS delivery passed against the built standalone frontend |
| Compose configuration | `docker compose --env-file .env.example config --quiet` passed |
| Docker image tags | Registry manifest lookup passed for PostgreSQL 17.11, Python 3.13.12 and Node 24.15.0 tags |
| Docker image builds / Compose startup | Not verified: Docker Desktop daemon reports it is unable to start |
| Hosted CI | Configured, not executed; no remote publication was authorized |
| Source/secret review | Source files inspected, credential/private-key pattern scan found no matches; local artifacts and dependencies ignored. Pattern scanning is not a full security audit |
| Git whitespace check | `git diff --check` passed; all source is untracked because there are no commits, so review used source inspection rather than a tracked diff |

The Docker exit criterion remains open. Native application/database startup was verified, but it does not prove the Compose images, PostgreSQL 17.11 runtime or Linux CI runner. Repair Docker Desktop, then run the exact Compose checks in README before accepting the full Phase 1 exit criterion.

Temporary backend/frontend processes were identified by their loopback listener PIDs and verified command lines, then stopped with `Stop-Process -Id 10980,34744`. The test database was stopped using `& 'C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe' -D artifacts\postgres16-test -m fast -w stop`. Ignored local test artifacts remain for inspection; no existing database was modified.

## Commands executed

Unless stated otherwise commands ran from the repository root in PowerShell. Environment assignments shown are test configuration, not real credentials. Read-only inspection also included `Get-Content` on the attached request and created source/configuration files, and `rg --files --hidden -g '!.git/**'` for the source inventory.

Initial inspection:

```powershell
Get-ChildItem -Force
rg --files -g AGENTS.md -g package.json -g README* -g pyproject.toml -g go.mod
git status --short
git log -1 --oneline
Get-Command docker,python,node,npm.cmd,uv -ErrorAction SilentlyContinue
docker version
docker context ls
python --version
node --version
npm.cmd --version
npm.cmd view next version
npm.cmd view react version
python -m pip index versions Django
Get-Command postgres,pg_ctl,psql -ErrorAction SilentlyContinue
Get-Service '*docker*' -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath 'C:\Program Files\PostgreSQL'
```

Backend install and checks:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.in
.\.venv\Scripts\python.exe -m pip freeze --local | Set-Content -Encoding ascii backend\requirements.lock
.\.venv\Scripts\ruff.exe check --fix backend scripts
.\.venv\Scripts\ruff.exe format backend scripts
.\.venv\Scripts\ruff.exe check backend scripts
.\.venv\Scripts\ruff.exe format --check backend scripts
$env:DJANGO_SETTINGS_MODULE='config.settings.test'
$env:TEST_SQLITE='1'
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py test operations
New-Item -ItemType Directory -Force artifacts
.\.venv\Scripts\python.exe backend\manage.py spectacular --validate --fail-on-warn --file artifacts\openapi.yaml
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip install --no-index -r backend\requirements.lock
.\.venv\Scripts\python.exe -m pip check
```

Temporary PostgreSQL verification (directory named `18` unexpectedly contained PostgreSQL 13.23; this temporary cluster was stopped and not used for Django tests):

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\postgres.exe' --version
& 'C:\Program Files\PostgreSQL\18\bin\initdb.exe' -D artifacts\postgres-test -U ppi --auth=trust --encoding=UTF8
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D artifacts\postgres-test -l artifacts\postgres-test.log -o '-h 127.0.0.1 -p 55432' -w start
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U ppi ppi
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D artifacts\postgres-test -m fast -w stop
& 'C:\Program Files\PostgreSQL\16\bin\postgres.exe' --version
& 'C:\Program Files\PostgreSQL\13\bin\postgres.exe' --version
& 'C:\Program Files\PostgreSQL\16\bin\initdb.exe' -D artifacts\postgres16-test -U ppi --auth=trust --encoding=UTF8
& 'C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe' -D artifacts\postgres16-test -l artifacts\postgres16-test.log -o '-h 127.0.0.1 -p 55432' -w start
& 'C:\Program Files\PostgreSQL\16\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U ppi ppi
$env:DJANGO_SETTINGS_MODULE='config.settings.test'
$env:POSTGRES_DB='ppi'
$env:POSTGRES_USER='ppi'
$env:POSTGRES_HOST='127.0.0.1'
$env:POSTGRES_PORT='55432'
Remove-Item Env:TEST_SQLITE -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe backend\manage.py migrate --noinput
.\.venv\Scripts\python.exe backend\manage.py migrate --check
.\.venv\Scripts\python.exe backend\manage.py test operations
.\.venv\Scripts\python.exe backend\manage.py spectacular --validate --fail-on-warn --file artifacts\openapi-postgres.yaml
```

Production check used `config.settings.production`, synthetic secret/password fixtures, `api.example.com`, HTTPS `https://app.example.com`, and the PostgreSQL variables above, then ran `.\.venv\Scripts\python.exe backend\manage.py check --deploy`. Production was not deployed and the synthetic configuration is not a security certification.

Frontend commands (working directory `frontend`):

```powershell
npm.cmd install --save-dev --save-exact typescript @types/node @types/react @types/react-dom eslint eslint-config-next@16.4.0 prettier vitest
npm.cmd audit --json
npm.cmd view eslint version
npm.cmd view typescript-eslint version peerDependencies
npm.cmd view braces version
npm.cmd uninstall eslint-config-next
npm.cmd install --save-dev --save-exact eslint@10.12.0 @eslint/js@10.0.1 typescript-eslint@8.71.2
npm.cmd install --save-dev --save-exact @types/node@24
npm.cmd run format
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
npm.cmd ci
npm.cmd audit --audit-level=high
New-Item -ItemType Directory -Force .next\standalone\.next
Copy-Item -LiteralPath .next\static -Destination .next\standalone\.next\static -Recurse -Force
$env:HOSTNAME='127.0.0.1'
$env:PORT='3000'
node .next\standalone\server.js
```

Live backend startup ran from `backend` with development settings and the loopback PostgreSQL variables above: `..\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`. HTTP requests used `Invoke-RestMethod` on the two backend health URLs. From the root, `.\.venv\Scripts\python.exe scripts\smoke.py` verified all three services and the landing CSS.

Infrastructure/review commands:

```powershell
docker compose --env-file .env.example config --quiet
docker manifest inspect postgres:17.11-bookworm
docker manifest inspect python:3.13.12-slim
docker manifest inspect node:24.15.0-bookworm-slim
git diff --check
git status --short --ignored
```

Manifests were discarded with `Out-Null`; nonzero exit codes stopped subsequent lookup commands. Source secret scan used PowerShell over `rg --files --hidden -g '!.git/**'` looking for PEM private keys, sk-proj credential patterns and AWS access key identifiers. npm debug-log tails were inspected while dependency installation was downloading.

## Failures and corrections

- Initial registry lookups failed with sandbox DNS restrictions; approved network access succeeded.
- Initial virtualenv initialization failed inside the sandbox; approved execution succeeded. Later sandbox Python commands printed a location warning but checks completed successfully. The no-index pip verification also emitted sandbox temporary-directory cleanup warnings.
- Docker API access initially denied; approved access revealed Docker Desktop's startup failure. No Docker image build/start success is claimed.
- Native PostgreSQL executables initially failed to launch under sandbox DLL restrictions; approved execution succeeded. A missing binary in the `13` directory was only a version probe.
- Local PostgreSQL connections were blocked by the sandbox; approved integration checks succeeded.
- First Ruff lint found one long test line; formatting fixed it and final checks passed.
- First frontend checks found a plain anchor navigation lint error and an obsolete Vitest `esbuild.jsx` option. Next Link and current Vitest configuration fixed both. Package module type removed the Vitest ESM warning.
- First production build compiled but had an EPERM standalone-copy warning. Approved final build completed without that warning. Explicit tracing root removed the unrelated parent lockfile warning.
- Initial npm audit reported five high findings through the lint configuration's braces/glob chain. Available braces 3.0.3 remained affected, so that unused lint dependency chain was replaced with supported ESLint/TypeScript ESLint. Final install reported zero findings; TypeScript, lint and tests passed with the replacement.
- Final log review removed Gunicorn's redundant raw access log and sanitized framework request messages that can contain query strings. The added regression test passed against PostgreSQL; structured application request logs remain available.

## Risks and precise next steps

1. Repair Docker Desktop and run README's Compose startup, migrations, tests, schema and smoke commands. PostgreSQL 17.11 and container runtime must still be exercised; CI must be run on a real remote runner.
2. Review the announced October 14 Next.js security patch before any production promotion. The announcement is on the [official Next.js blog](https://nextjs.org/blog). The registry returned Next.js 16.4.0 during implementation; a clean npm audit today does not promise future advisory coverage.
3. Production requires verified TLS ingress/header stripping, managed database/bucket/secret manager, image digest pins and scans, retention, backups, restore drills, alerts and domain-wide HSTS decisions. None is claimed deployed.
4. Start Phase 2 by deciding the custom user/identity model before initializing a customer database. Implement organizations, memberships, verified identity/invitations, deny-by-default role permissions, membership-derived tenant context and audit events. Prove cross-tenant access denial on all API/service paths before ingesting products. Do not implement a mock login and label it secure.

The full product/security/operations assumptions remain in the Phase 0 documents. PostgreSQL 17 was selected from the [official supported-version policy](https://www.postgresql.org/support/versioning/); native verification used 16.13 because that supported binary was installed locally.

## Exact created source-file inventory

All paths below are relative to the repository root. Temporary databases, exported schemas, build output, virtualenvs, caches and generated next-env.d.ts exist only in ignored locations.

```text
.env.example
.github/workflows/ci.yml
.gitignore
.python-version
README.md
compose.yaml
backend/.dockerignore
backend/Dockerfile
backend/manage.py
backend/pyproject.toml
backend/requirements.in
backend/requirements.lock
backend/config/__init__.py
backend/config/urls.py
backend/config/wsgi.py
backend/config/settings/__init__.py
backend/config/settings/base.py
backend/config/settings/development.py
backend/config/settings/environment.py
backend/config/settings/production.py
backend/config/settings/test.py
backend/operations/__init__.py
backend/operations/logging.py
backend/operations/middleware.py
backend/operations/tests.py
backend/operations/views.py
docs/product-requirements.md
docs/system-architecture.md
docs/domain-model.md
docs/security-threat-model.md
docs/testing-strategy.md
docs/deployment-and-operations.md
docs/implementation-report.md
docs/architecture-decisions/0001-modular-monolith.md
docs/architecture-decisions/0002-tenant-authorization.md
docs/architecture-decisions/0003-reproducible-assessments.md
docs/architecture-decisions/0004-defer-jobs-and-storage.md
docs/architecture-decisions/0005-environments-and-dependencies.md
frontend/.dockerignore
frontend/.node-version
frontend/.prettierignore
frontend/Dockerfile
frontend/eslint.config.mjs
frontend/next.config.ts
frontend/package.json
frontend/package-lock.json
frontend/tsconfig.json
frontend/vitest.config.ts
frontend/app/globals.css
frontend/app/layout.tsx
frontend/app/page.tsx
frontend/app/health/route.ts
frontend/tests/foundation.test.tsx
scripts/smoke.py
```
