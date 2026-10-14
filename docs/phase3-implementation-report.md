# Phase 3 implementation and verification

Date: 2026-10-14, Africa/Nairobi. Existing Phase 1/2 uncommitted changes were preserved. No staging, commit, push or deployment was performed.

## Delivered domain

The new `products` Django application implements:

- Organization-owned product UUIDs with immutable, tenant-unique, case-sensitive SKUs and owner/admin archival/reactivation.
- Immutable numbered complete product revisions with name, description, brand, manufacturer, model number, category, change reason, author and timestamps.
- Immutable revision-owned unit/inner/case/pallet packaging profiles, immediate containment counts, material/notes and nullable handling traits. Empty packaging and absent measurements remain unknown.
- Immutable observations of mass/length/width/height retaining original decimal values/units, canonical values/units, optional uncertainty bounds, observation method/time, conversion version and required evidence references. Multiple competing observations are retained without automatic selection.
- Immutable product-owned evidence metadata: source reference/type, optional declared SHA-256, attribution/license declarations, observation/recording times and author. `capture_status=reference_only` makes clear that no artifact or digest was verified. Immutable revision/evidence links include all measurement sources automatically.
- Paginated, non-cacheable product/revision/evidence/packaging APIs, strict serializers, read-only admin and transactional audit events with action/IDs rather than customer content.

Creation writes identity and revision 1 atomically. Later submissions append a complete snapshot; omitted fields are blank/unknown and not inherited. Writes resolve active membership, lock the organization, scope/lock the product and validate all evidence against that same product. Owner/admin/member may contribute structured records; owner/admin alone archive. Archived products retain readable history but reject new revisions/evidence. Revoked members, suspended tenants and nonmember staff cannot access the APIs. Every nested product/revision/profile/evidence identifier is scoped to its authorized parents. Audit failure rolls back business writes.

The additive `products/0001_initial` migration creates six tables and constraints for SKU/revision/source-link uniqueness, valid packaging levels/root/counts, positive measurement values, dimension-compatible units and enclosing uncertainty bounds. Existing identity/tenant/audit migrations were retained. No dependency changes were needed.

Metric-v1 uses exact Decimal factors: mm/cm/m → mm and g/kg → kg. Inputs accept up to 12 integer and six fractional digits; canonical columns retain up to 15 integer and nine fractional digits. This includes exact conversion of 0.000001 g to 0.000000001 kg. Nonfinite, nonpositive, overprecision and dimension-mismatched values are rejected. Bounds must both be omitted/null or both positive and enclose the reported value. No robot thresholds or safety outcomes were invented.

## API and documentation

See [API guide](product-api.md) for request examples and [ADR 0007](architecture-decisions/0007-product-revisions-and-reference-evidence.md) for policy decisions. Routes live under `/api/v1/organizations/{organization_id}/products/`: collection create/list, identity retrieve, state transition, revision create/list/detail, evidence create/list/detail and packaging list/detail. Historical PATCH/DELETE and generic identity editing are unsupported. Page size is 25. Invalid input is 400, session/role/CSRF denial 403, inaccessible scoped resources 404 and duplicate SKU 409.

Updated requirements, domain model, architecture, threat model, roadmap, README and test strategy. The landing disclosure now says product/packaging APIs are available while uploads and assessments remain unavailable. Product editing screens were not added. CI includes the products test module and a new product proxy smoke script.

## Executed verification

Commands ran from the repository root, with frontend commands in `frontend`. Native database checks used the existing isolated PostgreSQL 16.13 cluster on loopback port 55432 and fixture user `ppi`, with no `.env` secrets. PostgreSQL 17.11 Compose runtime remains an unverified separate environment.

| Check | Actual result |
| --- | --- |
| `manage.py test accounts organizations operations products --keepdb --verbosity 0` under test settings / isolated PostgreSQL | **56 tests passed**, including 19 product tests. Concurrent ownership and revision-number tests ran on PostgreSQL, not skipped. Ignored log: `artifacts/phase3-tests.log`. |
| Product tests | Tenant SKU uniqueness, original history persistence, exact conversion/uncertainty, conflicting observations, invalid units/precision/hierarchies, provenance validation, cross-tenant and same-tenant cross-product denial, nested revision/profile denial, role policy, revocation/suspension/staff denial, archival, immutable API/ORM paths, audit rollback, actor deletion retention, no source content in audit, pagination and real session CSRF all passed. |
| `manage.py spectacular --validate --fail-on-warn --file artifacts/openapi-phase3.yaml` | Passed without warnings/errors after explicit list operation IDs and a shared packaging-level enum name were added. |
| Dedicated `ppi_phase2_verification`: `migrate --noinput`, `migrate --check`, `makemigrations --check --dry-run` under development settings | Product migration applied successfully; no remaining migrations or model drift. Existing tables/history retained. |
| Frontend `npm run format:check`, `npm test`, `npm run lint`, `npm run typecheck` | Passed; **15 tests** across four files. |
| Frontend `npm run build` | Production standalone build passed. The first sandboxed attempt failed with Windows EPERM during standalone packaging; approved access outside the restricted sandbox completed successfully. |
| `python scripts/phase3_smoke.py --allow-create-test-data` | Passed against the built standalone frontend on port 3000 → dedicated Django development server on port 8001 → isolated PostgreSQL disposable DB. Real registration/login/session/CSRF, product creation/duplicate SKU, evidence, packaging observations, exact units, immutable history, cross-tenant/source denial, member contributions, archival/reactivation, revocation, audit and logout passed. |
| `python scripts/smoke.py` | Backend liveness/readiness, frontend health, updated landing disclosure and CSS passed. Port-8000 checks read the pre-existing development listener; product smoke used only the dedicated port-8001 backend. Native `.next/static` was copied into standalone before starting it, matching Docker packaging. |
| `python scripts/phase2_smoke.py --allow-create-test-data --read-cycles 50` | Passed against the final Phase 3 stack, including 200 repeated reads with no transport resets, cookie/CSRF/origin checks, tenant/role denial, revocation, logout and session replay denial. |
| `ruff format --check backend scripts`, `ruff check backend scripts` | Passed for 49 Python files. |
| `git diff --check`, staged names and tracked `.env` check | Passed; nothing staged, `.env` untracked/unchanged. |
| `docker compose config --quiet`, `docker compose build backend` | Passed; backend image includes the product code and migration. No runtime container acceptance is claimed. |

The initial product test run found a test-helper argument collision for malformed evidence UUIDs; renaming the fixture argument corrected the test before the passing full run. Initial schema validation found list/retrieve operation ID collisions and duplicate packaging enum naming; explicit schema names resolved them without silencing warnings. These were corrected before the final results above.

## Scope and release limits

Evidence provenance is metadata only. No file uploads, fetched URLs, private storage, quarantine/scanning, verified checksum, rights validation or artifact download exists. Source references alone cannot guarantee reproducible evidence. Product UI, observation sampling/selection workflow, constraints, assessments, extraction and exports remain deferred. All current roles contribute; specialized analyst/viewer roles were not invented.

Immutability and same-product link invariants are enforced through supported services/API, supplemental ORM guards and read-only admin. They are not protection against raw SQL, trusted operator writes or unsupported bulk ORM paths; no DB-level immutability trigger, cross-table tenant trigger or RLS is claimed. Organization locking conservatively serializes tenant writes and may require throughput measurement. Production quotas, product abuse limits, retention-aware correction/deletion, staging TLS/ingress and independent security/load review remain launch gates.

Docker startup was already blocked by exhausted address pools in Phase 2. Phase 3 verified image building and native execution; Docker PostgreSQL 17.11 runtime and hosted CI were not run. No networks, volumes, customer databases or unrelated processes were removed. Temporary fixture accounts/tenants/products/evidence remain in the disposable verification database. The pre-existing PostgreSQL and port-8000 listeners remain as found; only this phase's dedicated application servers are cleaned up.

## Files and reproducible checks

New: `backend/products/{models,serializers,services,views,urls,admin,tests}.py`, app/migration initializers, `products/migrations/0001_initial.py`, `scripts/phase3_smoke.py`, API guide, ADR 0007 and this report. Updated: installed apps/enum schema settings, root routing, CI commands, landing disclosure/test and foundation smoke, and current architecture/domain/security/testing/roadmap documentation. Existing Phase 2 files were preserved.

In a working Compose environment, after setup/start and database migration:

```powershell
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test accounts organizations operations products --settings=config.settings.test
docker compose exec -T backend python manage.py spectacular --validate --fail-on-warn --file /tmp/openapi.yaml
python scripts/phase2_smoke.py --allow-create-test-data
python scripts/phase3_smoke.py --allow-create-test-data
python scripts/smoke.py
```

Run smoke scripts only on a disposable database; they intentionally create and retain fixture data. Product requests use the same-origin `/api/v1/` transport and current CSRF token flow described in the API guide. Customer deployment still requires reviewed migrations, verified backups, production ingress and the remaining release gates above.
