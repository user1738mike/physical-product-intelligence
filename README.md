
# physical-product-intelligence
Multi-tenant SaaS platform that builds evidence-backed digital profiles of physical products and evaluates their compatibility with handling, inspection, packaging, and automation workflows.
# Physical Product Intelligence Cloud

A foundation for a multi-tenant product and packaging assessment platform, initially intended for warehouse robotics integrators. Phase 1 implements operational endpoints and a public identification page. Customer authentication, tenant data, uploads and assessment workflows are not yet implemented. Architecture and requirements are in [docs](docs/product-requirements.md).

## Local development (PowerShell, repository root)

Prerequisites: running Docker Desktop with Linux containers and Compose v2. Host Python 3.13 and Node 24 are optional for checks outside containers. Copy the placeholders, then edit `.env` with local-only values. No database port is exposed to the host.

```powershell
Copy-Item .env.example .env
notepad .env
docker compose config --quiet
docker compose up --build --wait --wait-timeout 240
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py migrate --check
python scripts/smoke.py
```

Open http://localhost:3000. Backend liveness is http://localhost:8000/api/v1/health/live/, database readiness is http://localhost:8000/api/v1/health/ready/, OpenAPI is http://localhost:8000/api/v1/schema/, frontend health is http://localhost:3000/health. Readiness does not check migrations; the explicit migration check above does. Use `docker compose logs -f backend frontend` to inspect logs. Backend source is mounted with reload; frontend source is baked into its development image: after edits run `docker compose up -d --build frontend`. This avoids host/container node_modules conflicts.

```powershell
docker compose exec -T backend ruff format --check .
docker compose exec -T backend ruff check .
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test --settings=config.settings.test
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
.\.venv\Scripts\python.exe backend\manage.py test operations
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

Phase 2 starts with a custom user/identity decision **before the first customer database is initialized**, organizations, memberships, role policy, membership-derived tenant context and audit events. Django's default auth tables currently exist only as framework foundation; changing user models later requires a migration plan. Implement verified login/invite/revocation flows, then prove two-tenant access denial on every list/detail/write/related-object path before ingesting product data.

Execution results and remaining blockers are recorded in `docs/implementation-report.md`.
