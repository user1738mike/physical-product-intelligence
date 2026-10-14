# Phase 3 completion report

Date: 2026-10-14, Africa/Nairobi. Repository: `C:\Users\HomePC\Desktop\Billion2\physical-product-intelligence`. Baseline: clean `main`, commit `c4d61b5` (`feat: Implement authentication and organization management features`). No commit, staging, push, deployment, database reset, volume deletion or unrelated project change was performed.

This completes the application scope of the full Phase 3 master task. Native PostgreSQL/application checks pass. Docker runtime acceptance remains blocked by host network-pool exhaustion; hosted CI and production ingress are not claimed as verified. The earlier [API foundation report](phase3-implementation-report.md) is historical and is superseded by this report.

## 1. Implemented functionality

Products now have a searchable/paginated tenant catalog, create/detail/edit workflows, lifecycle controls and reviewable history. Product PATCH appends a new immutable full revision and requires the expected revision, preventing stale overwrites. Tenant-unique, case-sensitive SKUs and organization ownership remain immutable. Existing members contribute catalog data; owner/admin controls lifecycle, physical verification and canonical selection.

Live named packaging configurations support unit/inner/case/pallet levels, optional units-per-package quantity, material, description, lifecycle, creator/modifier, timestamps and optimistic versions. Every successful descriptor/lifecycle change records an immutable ConfigurationRevision and an audit event. Multiple configurations at the same level are supported. Dimensions/mass are typed claims, not duplicate mutable columns. Unknown remains absent/null, never zero.

Evidence supports user entry, supplier documents, manufacturer specifications, imported catalog references, external AI/model estimates and physical-test references. Claims retain source metadata, value/unit, exact canonical normalization, uncertainty intervals, method, limitations, observation/recording times and actor. No AI pipeline or file fetching/upload is installed.

## 2. Actual model and schema changes

Existing Product, ProductRevision, PackagingProfile, Measurement, Evidence and RevisionEvidence tables/migration 0001 were preserved. Product summary fields are derived from revisions rather than duplicated on Product. `modified_by_id` refers to the latest catalog revision's author; lifecycle actors are in audit history.

Migration `products/0002_catalog_workflows_and_attribute_claims` adds five tables:

| Model | Purpose and constraints |
| --- | --- |
| PackagingConfiguration | Stable product-owned UUID, required bounded name/level, nullable positive quantity, descriptors, active state, positive version, actor/timestamps; unique product/name; product/state index |
| ConfigurationRevision | Immutable full descriptor/lifecycle snapshot and reason/actor/time; unique packaging/version |
| AttributeClaim | Immutable product/profile assertion; allowlisted numeric/text attributes; reported/estimated/measured basis; positive finite typed values, compatible units, enclosing intervals, method/limitations, source/actor/time; resource/attribute index |
| ClaimVerification | Immutable original/measured claim relationship, authorized actor/server time, instrument/procedure/notes; distinct claims and unique measured-claim reference |
| ClaimSelection | Immutable selected claim, actor/server time and rationale |

The migration expands evidence source choices with manufacturer_spec, imported_catalog and ai_estimate, replacing its source check safely, and adds a product/active-state/update index. No dependency or authentication-model change was needed.

Migration `products/0003_postgres_provenance_guards` installs a reversible PostgreSQL function and five deferred constraint triggers. They check same-product revision/source and measurement/source links, same-revision ordered bundled containment, claim/source/profile ownership and verification scope/attribute consistency. A measured claim must have its verification by transaction commit. These guards are PostgreSQL-specific, not RLS or database-level immutability; SQLite does not install them. Operators remain trusted.

Migration `products/0004_finite_physical_values` adds finite upper bounds matching the original/canonical decimal columns' representable ranges. This also rejects PostgreSQL numeric NaN through direct SQL, supplementing API and ORM validation without introducing arbitrary physical safety limits.

Original bundled PackagingProfile snapshots remain at revision routes and were not renamed/deleted/automatically merged into live configurations. Live configuration quantity is units per package; legacy bundled hierarchy quantity keeps its original immediate-containment meaning. ADR 0008 documents the distinction and compatibility decision.

## 3. APIs added or extended

All routes retain `/api/v1/organizations/{organization_id}/products/`, current session/CSRF, active membership, parent scoping and non-cacheable responses. Unknown/system-owned payload fields are rejected. Errors: 400 validation, 403 session/role/CSRF denial, 404 inaccessible scoped resources, 409 duplicate/stale write, 405 unsupported mutation/deletion. Collections use 25-item pages.

| Method / relative route | Behavior |
| --- | --- |
| GET collection | Validated search by SKU/current name, lifecycle filter and allowlisted ordering with stable UUID tie-breaker |
| PATCH `{product}/` | Descriptive edit with expected_revision/change_reason; append full revision |
| GET/POST `{product}/packaging/` | Live packaging list/create |
| GET/PATCH `{product}/packaging/{pack}/` | Scoped profile/detail/edit with expected_version |
| POST `{product}/packaging/{pack}/state/` | Owner/admin archive/reactivate |
| GET `{product}/packaging/{pack}/revisions/` | Immutable descriptor/lifecycle versions |
| GET `{product}/packaging/{pack}/evidence/` | Distinct sources referenced by that profile's claims |
| GET/POST `scope/claims/` | Immutable reported/estimated attribute assertions, optionally atomic source creation |
| GET `scope/claims/{claim}/` | Assertion, source and verification records |
| POST `scope/claims/{claim}/verification/` | Owner/admin documented physical measurement; separate measured claim |
| GET `scope/attributes/` | Nine fixed attribute states, conflicts and explicit selection |
| POST `scope/attributes/{attribute}/selection/` | Owner/admin decision/rationale |
| GET `scope/history/` | Member-readable product/profile success history with no mutation endpoint |

Here scope is a product or its live packaging profile. Existing product creation/state/revision/evidence and bundled-snapshot APIs remain compatible. Historical revisions/claims/evidence have no PATCH/DELETE; product and live profile deletion remain unavailable. Catalog search is at most 100 characters; page/query choices, nested lists and bodies are bounded. A resource cannot exceed 500 retained claims. See [API examples](product-api.md).

## 4. Frontend workflows

The new `/products` entry lists authorized organizations with pagination. Organization-specific routes provide catalog search/filter/order/pagination, product creation, detail and edit. The detail page includes catalog metadata, live packaging creation/edit/lifecycle, scoped attribute quality, evidence forms/cards, physical-measurement attestation, selection rationale, descriptor versions and audit history.

Forms use typed clients, same-origin cookies and fresh masked CSRF per mutation. No session secret is stored in localStorage. Required/unknown values, units, reported metadata, estimated claims, physical attestations and unresolved/resolved disagreements are visibly distinct. Loading, empty, validation, network/API errors, disabled saving states, keyboard controls, labels/table headers and focusable error feedback are implemented. Numeric physical values are submitted as decimal strings.

Browser verification used disposable local accounts, an organization, a product and packaging records. Product create/edit, 27-record catalog paging, SKU search, packaging create/edit, reported and estimated claims, physical verification, rationale selection, archive/reactivate, history, scope switching, member controls and invalid-zero error focus were actually exercised. It found duplicate sibling React keys retaining an old workspace; unique prefixes fixed it. Both development verification and the final production build showed exactly one evidence workspace, retained estimates, and no member verification controls. Error feedback focused the alert paragraph and retained prior claims. The final production screenshot is in ignored `artifacts/phase3-catalog-evidence.png`.

This is functional browser verification and basic form/accessibility review, not a formal WCAG certification, mobile/device matrix or independent accessibility audit.

## 5. Tenant isolation and authorization results

Phase 2 baseline authentication/tenant tests passed before implementation. No confirmed critical Phase 2 tenant-isolation vulnerability was found. The existing proxy is a fixed-origin API route, preserves cookies/CSRF/Origin and trailing slashes, bounds bodies and does not replay failed mutations. The final authentication smoke passed 200 consecutive CSRF/profile reads without resets.

Every new endpoint resolves the authorized active organization through existing membership services, then scopes product/profile/claim/source/history. Writes lock the organization before resources, serializing with membership/role changes. Client organization/product/actor/status injection is rejected. Foreign source/profile/claim identifiers are rejected even across products in one tenant. Staff has no bypass. Product/profile archival stops new writes while retaining reads; suspension and revoked membership deny protected resources. Verification/selection/lifecycle require owner/admin. Members can contribute and read resource-scoped history while global organization audit remains restricted.

PostgreSQL integration tests verify authorized access separately from cross-tenant denials, stale writes, concurrent edits, direct ORM provenance violations, and unbacked measured claims. Audit failures roll back domain writes and success events. Source content and credentials are not audit metadata.

## 6. Provenance, verification and conflict behavior

Direct assertions accept reported/estimated only. Estimates require method/version/limitations; AI references cannot become reported by changing a field. Numeric dimensions accept mm/cm/m → mm; mass accepts g/kg → kg. Original/canonical decimals and intervals are retained under metric-v1. Inputs permit 12 integer and six fractional digits, canonical storage 15 integer and nine fractional digits, with no silent rounding. Zero/negative/nonfinite, incompatible/missing units, overprecision, partial bounds and non-enclosing bounds are rejected. Text assertions cannot carry numeric values or units. No comparable confidence scalar is invented.

Owner/admin verification requires numeric observation/unit/time, physical_test source, instrument, procedure and limitations/sampling notes. It creates a new measured claim and immutable verification with actor/server time; the original estimated/reported claim remains unchanged. This is an authorized physical-measurement attestation, not independently verified reality, artifact integrity or safety certification. Old contributor-declared measured methods are explicitly `unverified_report`.

Competing values/intervals/text remain separate. Only an owner/admin selection with rationale supplies a canonical attribute value. Selecting an estimate retains its estimated basis. A later matching observation preserves the selection; a later contradictory one reopens conflict and withholds the canonical value until renewed review. All selection/claim records persist. Catalog text is not automatically replaced by a selection.

## 7. Migration status and data preservation

All three new migrations applied successfully to the isolated PostgreSQL 16.13 database `ppi_phase2_verification` on loopback 55432. Before/after counts were compared at each migration boundary; existing records were preserved. After 0003, preserved counts were: users 10, organizations 9, memberships 11, products 29, product revisions 32, evidence 5, live packaging 1, configuration revisions 4, claims 3, verification 1, selection 1. Later smoke fixtures intentionally add records; these counts are the migration-boundary evidence, not a promised final fixture count.

Migration consistency/system/schema checks pass. No existing migration was rewritten; 0001 remains intact. During development, the new PostgreSQL trigger function's record-field branching was corrected and replaced only in the isolated test database, without a database reset/deletion; the passing suite and native smoke exercised the corrected function. Migration 0003 remains additive/reversible and was not customer-deployed. Test-only rows, databases and ignored artifacts remain; no Docker volumes or customer databases were deleted.

## 8. Actual checks and results

| Command / executed check | Actual result |
| --- | --- |
| Baseline `git status`, branch/log, diffs/docs/models/services/migrations inspection | Clean main/c4d61b5; baseline existing work retained |
| Baseline PostgreSQL tests | 56 passed |
| Baseline frontend tests | 15 passed |
| Final PostgreSQL `manage.py test accounts organizations operations products --keepdb --verbosity 0` | **75 passed**, including ownership/revision/concurrent stale-edit tests and PostgreSQL provenance triggers; no SQLite substitution. Ignored `artifacts/phase3-complete-tests.log` |
| `ruff check backend scripts`, `ruff format --check backend scripts` | Passed after formatting new Python files |
| `manage.py check`, `migrate --check`, `makemigrations --check --dry-run` | Passed; no system errors/model drift/unapplied fixture migrations |
| `manage.py spectacular --validate --fail-on-warn --file artifacts/openapi-phase3-complete.yaml` | Passed without warnings/errors; request/response serializers and search/query schema included |
| Frontend `npm.cmd test` | **22 passed** in five files |
| Frontend `npm.cmd run typecheck`, `lint`, `format:check` | Passed. Next path canonicalization initially required approved filesystem access. Prettier now preserves checked-out line endings; 14 verified EOL-only files were restored to their original Windows checkout line endings instead of leaving unrelated changes |
| Frontend `npm.cmd run build` | Final standalone production build passed, including catalog/list/new/detail/edit routes |
| Expanded `python scripts/phase3_smoke.py --allow-create-test-data` | Passed through final production proxy and PostgreSQL, including typed claims, physical verification, conflict selection/matching/new-conflict behavior, lifecycle, nested denial and scoped history |
| `python scripts/phase2_smoke.py --allow-create-test-data --read-cycles 50` | Passed registration/login/cookies/CSRF/origin denial, 200 reads, tenant/role denial, revocation, logout/replay denial |
| `python scripts/smoke.py` | Passed backend live/readiness, frontend health, landing disclosure and CSS. Port 8000 was the pre-existing read-only health listener; domain smoke used dedicated backend 8001 |
| Real browser actions using local fixture accounts | Workflows listed in section 4 passed; final production scope/role check passed after reopening a fresh tab when the old tab retained the expected stopped-dev-server error page |
| `docker compose up --build -d` | Both application images built; startup failed at network allocation with `all predefined address pools have been fully subnetted` |
| Final `docker compose build backend` after the last runtime backend change | Passed; final backend image includes all three new migrations and corrected conflict behavior |
| `git diff --check`, staging and tracked `.env` inspection | Passed; no staging/commit/push or `.env` change |
| Production `manage.py check --deploy` with synthetic settings; `python -m pip check` | No deployment errors; only existing W005/W021 HSTS subdomain/preload warnings. No broken Python requirements. No real production TLS was exercised |

Temporary hidden application listeners used loopback 3000/8001 and only the dedicated disposable PostgreSQL database. Server PIDs/commands were validated before stopping/restarting them. The pre-existing PostgreSQL cluster/port-8000 listener were retained. No unrelated process/network/volume was changed.

## 9. Docker and PostgreSQL status

PostgreSQL **16.13 native** migrations/integration/concurrency/constraint checks executed and passed. PostgreSQL **17.11 Compose runtime** did not execute because network creation remains blocked. Image building and successful native execution are not claimed as container acceptance. No address-pool pruning, custom subnet workaround or volume deletion was attempted. Docker locks/API access initially required approved execution outside the sandbox; the final recorded failure is the host's subnet-pool exhaustion, not application startup success.

## 10. CI status

The existing workflow already discovers the products app and frontend tests. It now explicitly checks applied backend migrations. The existing Phase 3 smoke was expanded to cover all new domain workflows without creating an extra registration batch that would exceed signup throttling. PostgreSQL CI remains configured for 17.11; the Compose job runs Phase 2/3 smoke and frontend build checks. **Hosted CI was not run** because no commit/push was authorized. Local executed results are above; runner/container/TLS behavior is not inferred from configuration.

## 11. Files changed and final Git state

New backend files: products migrations 0002/0003/0004, `workflow_serializers.py`, `workflow_views.py`, `workflows.py`, `test_workflows.py`. Extended existing product models/services/serializers/views/routes/admin/tests. No requirements/lockfile/auth model changed.

New frontend files: typed `lib/products.ts`, shared `app/products/{catalog,detail,evidence,ui}.tsx`, workspace page, organization-specific list/new/detail/edit route wrappers, `tests/products.test.tsx` and `.prettierrc.json` for cross-platform EOL preservation. Account/landing navigation, styles, typed error extraction and TS path alias were updated. `frontend/AGENTS.md` was generated by Next dev and retained; its installed-version guides were read. Unchanged frontend files were restored to the original Windows checkout line endings after verifying normalized content was identical to HEAD. Git's cached metadata was refreshed without staging content.

Updated CI/smoke/docs include README, API/domain/requirements/security/architecture/testing/roadmap, ADR 0007 completion note, new ADR 0008, this completion report and historical report pointer. Requested nested documentation paths now point to the maintained canonical documents. The final exact Git snapshot appears below; all task changes remain unstaged on main.

```text
 M .github/workflows/ci.yml
 M README.md
 M backend/products/admin.py
 M backend/products/models.py
 M backend/products/serializers.py
 M backend/products/services.py
 M backend/products/tests.py
 M backend/products/urls.py
 M backend/products/views.py
 M docs/architecture-decisions/0007-product-revisions-and-reference-evidence.md
 M docs/domain-model.md
 M docs/engineering/phase-roadmap.md
 M docs/phase3-implementation-report.md
 M docs/product-api.md
 M docs/product-requirements.md
 M docs/security-threat-model.md
 M docs/system-architecture.md
 M docs/testing-strategy.md
 M frontend/app/account/account.tsx
 M frontend/app/globals.css
 M frontend/app/page.tsx
 M frontend/lib/api.ts
 M frontend/tsconfig.json
 M scripts/phase3_smoke.py
?? backend/products/migrations/0002_catalog_workflows_and_attribute_claims.py
?? backend/products/migrations/0003_postgres_provenance_guards.py
?? backend/products/migrations/0004_finite_physical_values.py
?? backend/products/test_workflows.py
?? backend/products/workflow_serializers.py
?? backend/products/workflow_views.py
?? backend/products/workflows.py
?? docs/architecture-decisions/0008-catalog-workflows-and-attribute-verification.md
?? docs/architecture/system-architecture.md
?? docs/phase3-completion-report.md
?? docs/product/product-requirements.md
?? docs/security/threat-model.md
?? frontend/.prettierrc.json
?? frontend/AGENTS.md
?? frontend/app/organizations/[organizationId]/products/[productId]/edit/page.tsx
?? frontend/app/organizations/[organizationId]/products/[productId]/page.tsx
?? frontend/app/organizations/[organizationId]/products/new/page.tsx
?? frontend/app/organizations/[organizationId]/products/page.tsx
?? frontend/app/products/catalog.tsx
?? frontend/app/products/detail.tsx
?? frontend/app/products/evidence.tsx
?? frontend/app/products/page.tsx
?? frontend/app/products/ui.tsx
?? frontend/lib/products.ts
?? frontend/tests/products.test.tsx
```

## 12. Known limits and deferred work

- Docker runtime and hosted CI remain unverified as described above; production TLS/ingress/staging verification is separate.
- No file upload/fetch/quarantine/private-storage adapter, verified checksum, license verification, AI extraction, compatibility engine, rules/assessments, billing, analytics dashboard or Phase 4 implementation.
- Physical verification records an authorized attestation with evidence details, not independent laboratory/real-world verification. Text attributes are reported/estimated/selected; physical verification is limited to numeric dimensions/mass.
- Legacy bundled packaging snapshots remain accessible through revision APIs, independently of the current editable configuration collection; no automatic migration/merge invents identities or values.
- No hard deletion/purge pipeline or final retention/legal-hold policy; references/history are protected. No RLS or DB-level append-only guarantee against trusted operators. SQLite cannot prove PostgreSQL guards or row locks.
- Claim histories are capped at 500 per resource; product quotas, distributed abuse limits and large-catalog performance/load review remain launch work. No availability/SLO or formal accessibility certification is claimed.

## 13. Exact startup and test commands

From the repository root, for the normal development Compose environment once the host pool issue is resolved:

```powershell
python scripts/setup_env.py
docker compose config --quiet
docker compose up --build --wait --wait-timeout 240
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test accounts organizations operations products --settings=config.settings.test
docker compose exec -T backend python manage.py spectacular --validate --fail-on-warn --file /tmp/openapi.yaml
python scripts/phase2_smoke.py --allow-create-test-data
python scripts/phase3_smoke.py --allow-create-test-data
python scripts/smoke.py
```

Run smoke only against a disposable database; it intentionally creates and retains test accounts, tenants, sources, products and claims. Do not execute on customer data. Existing `.env` is preserved by setup; do not change credentials for an already initialized volume casually. `docker compose down` stops this project while preserving volumes; no volume-removal command is needed.

Native PostgreSQL commands used for backend verification (the isolated cluster was already running):

```powershell
$env:DJANGO_SETTINGS_MODULE='config.settings.test'
$env:POSTGRES_HOST='127.0.0.1'
$env:POSTGRES_PORT='55432'
$env:POSTGRES_USER='ppi'
$env:POSTGRES_DB='ppi'
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py test accounts organizations operations products --keepdb --verbosity 0
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py spectacular --validate --fail-on-warn --file artifacts/openapi-phase3-complete.yaml
.\.venv\Scripts\ruff.exe check backend scripts
.\.venv\Scripts\ruff.exe format --check backend scripts
```

For native HTTP/browser verification, in a separate root terminal use the same isolated host/port/user but `POSTGRES_DB=ppi_phase2_verification` and `DJANGO_SETTINGS_MODULE=config.settings.development`, then run migration and `python backend/manage.py runserver 127.0.0.1:8001 --noreload`. This is the disposable fixture database, not the local `.env` database. In another terminal:

```powershell
Set-Location frontend
npm.cmd run format:check
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
New-Item -ItemType Directory -Force .next/standalone/.next/static | Out-Null
Copy-Item -Path .next/static/* -Destination .next/standalone/.next/static -Recurse -Force
$env:API_BACKEND_ORIGIN='http://127.0.0.1:8001'
$env:HOSTNAME='127.0.0.1'
$env:PORT='3000'
npm.cmd run start
```

Open `http://127.0.0.1:3000/products`, sign in through Account, choose an authorized organization and enter its catalog. Configure real production infrastructure separately with reviewed backups, migration release steps and HTTPS origins.

## 14. Acceptance checklist

- [x] Product/live packaging/evidence/claims/history scoped by current tenant membership.
- [x] Same SKU accepted across tenants and rejected within one tenant; required fields/lengths enforced.
- [x] Explicit positive finite dimensions/mass/units and exact normalization/precision/bounds; unknowns remain unknown.
- [x] Reported/estimated/physically verified assertions, source metadata, actor/time/procedure preserved.
- [x] Unauthorized estimate promotion denied; original estimates retained after new measurements.
- [x] Conflicts retained, explicit rationale selection, matching claims preserved and new contradictions reopen review.
- [x] Reliable immutable product/configuration/claim/verification/selection history and safe audit events.
- [x] Cross-tenant/nested-resource/role/concurrent-edit tests pass on PostgreSQL.
- [x] Real catalog/create/edit/packaging/search/pagination/evidence/verification/lifecycle/error/member browser workflows pass.
- [x] Existing Phase 1/2 regressions and final proxy/auth smoke pass.
- [x] Additive migrations preserve records; consistency and OpenAPI validated.
- [x] Frontend tests/type/lint/format/production build pass; documentation and CI updated.
- [ ] Docker PostgreSQL 17.11 container runtime acceptance — host address pools exhausted.
- [ ] Hosted CI and real production TLS/ingress/independent release review — not executed.

No Phase 4 work, commit or push was performed.
