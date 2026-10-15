# Phase 5 implementation and verification report

Date: 2026-10-15. Scope: equipment profiles, versioned declarative compatibility rules and explainable immutable assessments. Phase 6 was not started.

## A. Repository audit

The working tree was clean on `main` at `8738106` before this phase. Actual committed code included session/CSRF authentication, membership-derived tenant authorization, owner/admin/member services and transactional audit; product identities/revisions, live packaging/history, exact metric claims, reference provenance, physical attestations, canonical decisions/conflicts; and private bounded ingestion with review, approval and atomic application. Models, migrations, services, API routes, frontend routes and earlier reports were inspected; prior prompts were not treated as evidence.

The baseline PostgreSQL suite passed **98 tests**, and the frontend passed **26 tests**. Phase 2/3/4 foundations were sufficiently sound for integration. No prerequisite repair, duplicate tenant/product/packaging/evidence/audit model, database reset or dependency addition was needed. Phase 5 reuses their authorization, locks, converters, evidence snapshots and private source access.

## B. Implementation

New Django module `compatibility` contains:

- Equipment: stable UUID/tenant/code identity, draft/active/archived state, optimistic edit version, actor/time; EquipmentRevision: immutable numbered complete definition and reason.
- RuleSet: immutable numbered typed JSON bound to an exact equipment revision, evidence policy and schema version; RuleActivation: separate immutable approval/actor/time/reason.
- Assessment: immutable organization/request UUID, actor/time, exact product/package/equipment revisions, rules, frozen claim/provenance inputs, results, engine version and optional same-target parent.
- Additive migration `0001_initial` creates tables/indexes/uniqueness; reversible PostgreSQL migration `0002_scope_guards` validates structural specification and assessment reference scope. No existing tables or data are removed.

Owner/admin equipment edits append specifications and return to draft. Rules are revised by creating another immutable set; activation requires current documented context/levels, at least one enabled hard rule and specification provenance for all enabled rules. Explicit known AI-estimate evidence cannot authorize equipment constraints. Previously activated sets remain eligible only while bound to the current specification; multiple eligible versions require explicit selection. Archive/restore appends history and requires new rules before reactivation.

The pure `warehouse-fit-v1` engine executes an allowlist: numeric minimum/maximum/required attribute, packaging-level membership and explicit orientation. Decimal mm/cm/m and g/kg use existing `metric-v1` conversions. Boundaries are inclusive; maximum clearance subtracts from the limit, minimum clearance adds. Intervals crossing a limit remain indeterminate. Only explicit length/width swapping is supported. There is no expression evaluator, AI judgment or external call.

Compatible requires an explicit allowed handling level/orientation where applicable, sufficient nonestimated evidence, consistent claims, passing hard checks and hard maxima for all length/width/height/mass. Missing maxima produce unknown checks rather than unlimited capacity. A reliable hard failure establishes incompatible even if other inputs remain unresolved; otherwise unresolved hard checks yield indeterminate. Advisory failures are retained but nonbinding. Canonical editorial decisions do not erase conflicts. Measured-only policy requires existing physical attestation records. Original values/units, canonical bounds, effective limits, source references and uncertainty explanations are retained.

One organization-locked transactional service records assessment plus audit, validates all nested references and preserves retry identity. Same key/same operands returns the original result; changed operands conflict. New evaluations use new keys and optional parents. Historical reads use frozen JSON without reevaluation. Comparison aligns stable rule IDs and returns retained before/after results for matching targets. No normal update/delete endpoints exist. Supported ORM snapshot guards supplement APIs; database operators remain trusted.

Tenant API endpoints under `/api/v1/organizations/{id}/` provide equipment collection/detail/state/revisions, rule-set collection/detail/activation and assessment collection/detail/compare. Active members read/run; only owner/admin manages equipment and activation. Current membership, suspension, nested scope, session and CSRF checks remain authoritative. Audit records include equipment creation/revision/state, rule revision/activation and evaluation creation. History pages omit large JSON and have bounded query-count tests. Payload/rule/claim limits and per-process throttling bound ordinary work.

Next.js adds equipment search/filter/pagination/create/detail/edit/archive/history and typed rule editing/version cloning/activation. Assessments offer product/equipment search, package scope, explicit orientation/level, eligible version selection, run/results, evidence quality/provenance and immutable history/filter/parent/comparison views. Existing tenant navigation, form errors, focus handling and style system are reused. Final browser testing found and fixed asynchronous package-prefill loss during reassessment. Constraint display now explains retained effective limits in ordinary language. Landing/account availability copy reflects actual behavior and explicitly disclaims safety certification.

The [API guide](compatibility-api.md) contains lifecycle/permission tables, exact semantics, request examples, missing-input example and limits. [ADR 0010](architecture-decisions/0010-versioned-equipment-and-deterministic-assessments.md) records design choices. Canonical architecture/domain/requirements/threat/testing/roadmap documents and their nested pointers are updated.

## C. Verification

Actual final results:

| Check | Result |
| --- | --- |
| Full backend on native PostgreSQL 16.13 | **132 passed**, including 34 compatibility tests; no skips claimed as PostgreSQL proof |
| Frontend Vitest | **32 passed**, seven files |
| Setup regression | **4 passed** |
| Python dependency consistency | `No broken requirements found` |
| Ruff lint / format | Passed; 82 Python files formatted |
| Django system check | No issues |
| Applied migration check / drift | Passed / no changes detected |
| OpenAPI validation, fail on warning | Passed without warnings |
| Frontend lint / typecheck / format | Passed |
| Final Next.js production build | Passed; all four new equipment/assessment routes emitted |
| Authentication live smoke | Passed, including 200 repeated reads and logout/replay/origin/CSRF/cookie/role/tenant/revocation checks |
| Combined catalog/ingestion/compatibility proxy smoke | Passed against production Next.js and native Django |
| Health / landing / generated CSS | Passed; dedicated Phase 5 backend 8001 separately checked |
| Docker application images | Built successfully during Compose attempt |
| Compose runtime | **Blocked:** all predefined address pools fully subnetted |
| Hosted CI | Updated configuration; **not executed** in this task |

Native checks used the existing loopback PostgreSQL cluster on port 55432. The application verification database is `ppi_phase2_verification`; tests use Django's isolated test database. No secrets were printed and `.env` was preserved. Full-suite log: `artifacts/phase5-final-tests.log` (`Ran 132 tests in 134.943s`, `OK`). Migration preservation: `artifacts/phase5-migration-counts.json`. Before/after counts matched for every existing business table: users 24, organizations 23, memberships 25, audit 503, products 42, evidence 23, product revisions 63, revision evidence 9, bundled packaging 12, measurements 6, live packaging 9, configuration revisions 27, claims 29, verifications 6, selections 9, import jobs 6, import rows 4, candidates 14 and reviews 19. New content types (+5) and permissions (+20) are expected Django metadata. Later smoke/browser fixtures intentionally increase counts.

### Commands executed

From repository root unless noted. Native PostgreSQL environment used `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=55432`, `POSTGRES_USER=ppi`, appropriate existing database and `DJANGO_SETTINGS_MODULE=config.settings.test` for tests/checks; development settings for native HTTP. The schema/check commands were also rerun against `ppi_phase2_verification` at the end.

```powershell
.\.venv\Scripts\python.exe backend/manage.py test accounts organizations operations products ingestion --settings=config.settings.test
.\.venv\Scripts\python.exe backend/manage.py test compatibility --settings=config.settings.test
.\.venv\Scripts\python.exe backend/manage.py test accounts organizations operations products ingestion compatibility --settings=config.settings.test
.\.venv\Scripts\python.exe backend/manage.py migrate --noinput
.\.venv\Scripts\python.exe backend/manage.py migrate --check
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py spectacular --validate --fail-on-warn --file artifacts/openapi-phase5.yaml
.\.venv\Scripts\ruff.exe check backend scripts
.\.venv\Scripts\ruff.exe format --check backend scripts
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p test_setup_env.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/phase2_smoke.py --allow-create-test-data --read-cycles 50
.\.venv\Scripts\python.exe scripts/phase3_smoke.py --allow-create-test-data
.\.venv\Scripts\python.exe scripts/smoke.py
docker compose up --build -d
git diff --check
git status --short
```

Frontend working directory:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run format:check
npm.cmd run build
Copy-Item -LiteralPath .next/static -Destination .next/standalone/.next/static -Recurse -Force
```

Temporary runtime used `python manage.py runserver 127.0.0.1:8001 --noreload` and `node .next/standalone/server.js`, frontend port 3000 and server-only origin `http://127.0.0.1:8001`. PowerShell launched them hidden with log redirection. `scripts/smoke.py` has historical port 8000 hardcoded, so its two backend health results concern the preexisting listener; a separate urllib check verified both dedicated 8001 health endpoints. Its frontend health, landing and CSS checks concern the final production build. Existing listeners and PostgreSQL were preserved.

Verification exposed normal implementation issues that were fixed: initial schema component naming collisions, formatting issues, AI specification activation protection and the reassessment package-prefill race. Final checks above supersede diagnostic runs. Windows sandbox temp-file access initially caused setup errors and route-type generation access denial; the same checks passed with approved access. A rebuild initially encountered EBUSY while the production server held its output directory; stopping only the verified temporary server allowed the final build to pass. No tests/security assertions were weakened.

### Live and browser evidence

`artifacts/phase5-auth-smoke.log` records the Phase 2 regression pass. `artifacts/phase5-proxy-smoke.log` records Phase 3/4/5 success using the same two fixture users: draft/activation, missing→indeterminate, full reported→compatible, contradictory→indeterminate despite favorable canonical selection, tighter rules→incompatible, retained historical snapshot, retry identity, comparison, source privacy and tenant/role/CSRF denial.

Real browser verification on the final production frontend created `UI-CONVEYOR-001` with four explicitly synthetic documented maxima, saved rule version 1 and activated it. It selected the preexisting imported carton and shipping case, ran a retained assessment, then reassessed through the parent flow and compared results. Both snapshots show 2 pass/3 indeterminate: reported mass qualifies; missing length/width/height do not. Package prefill and explicit orientation were retained; comparison showed zero changed rule results. The screen visibly distinguishes reported input and safety limits. Screenshot: `artifacts/phase5-assessment.png`. These synthetic fixtures are retained in the disposable local database; no customer record was overwritten. No formal full accessibility or exhaustive responsive/browser matrix is claimed.

Compose built both application images but could not create this project's default network. No networks/volumes were pruned, no subnet workaround was introduced and no unrelated Docker project was changed. Compose PostgreSQL 17.11 runtime and hosted CI are unverified. Native PostgreSQL passing checks are not represented as container acceptance or production deployment.

The temporary browser tab and verified Phase 5 frontend/backend processes were closed after verification; ports 3000/8001 no longer had listening verification servers. The existing PostgreSQL cluster and unrelated services were left running.

## D. Known limitations

Static envelope assessment only: metric dimensions/mass, four required hard maxima, explicit packaging level and horizontal orientation swap. Shape, friction, center of gravity, gripper reliability, dynamic loading, stability, container geometry and safety/regulatory certification are unsupported. No imperial conversion or free-text/legacy bundled-measurement inference is included. Partial specifications remain useful for failure/unknown explanations but cannot pass a full envelope.

Sources reuse existing evidence/imports and frozen metadata; manufacturer authenticity and physical correctness remain unverified. A physical attestation is not automatically independent laboratory evidence. File links require current authorization and retention; external mutable references alone are not captured bytes. Existing production private storage/scanner, durable processing, retention/purge, distributed abuse protection, TLS ingress, backups/restore and dependency/image release review remain gates. Per-process throttling is best effort. Database structural guards are not RLS or privileged-operator immutability.

The initial bounds are 30 rules, 100 numeric claims per chosen scope, 64 KiB ordinary mutation bodies, 25-row pages and 60/hour assessment collection requests. Oversized histories reject rather than truncate. Performance at customer scale, sampling policy and real equipment/customer acceptance require separate validation. No new infrastructure, dependencies or general workflow engine was added.

## E. Important changed files

| Files | Purpose |
| --- | --- |
| backend/compatibility/models.py; migrations/0001_initial.py; migrations/0002_scope_guards.py | Equipment, immutable rules/assessments, indexes and PostgreSQL reference guards |
| backend/compatibility/engine.py | Pure Decimal evaluation and explicit evidence sufficiency |
| backend/compatibility/services.py | Authorized transactional lifecycle, activation, snapshot, retry and comparison |
| backend/compatibility/serializers.py; views.py; urls.py | Strict operands, bounded queries and tenant API/OpenAPI |
| backend/compatibility/tests.py | Engine/API/role/tenant/history/rollback/concurrency tests |
| backend/config/settings/base.py; config/urls.py | Module, throttle and unambiguous schema integration |
| frontend/lib/compatibility.ts | Typed API transport using existing fresh CSRF |
| frontend/app/compatibility/equipment.tsx; assessments.tsx | Functional equipment/rule and assessment/history workflows |
| frontend/app/organizations/[organizationId]/equipment/**; assessments/** | Four tenant route wrappers |
| frontend/app/products/ui.tsx; globals.css; page.tsx; account/account.tsx | Navigation, responsive styles and accurate availability |
| frontend/tests/compatibility.test.tsx; foundation.test.tsx | Retained limits, evidence/escaping/transport and availability tests |
| scripts/phase5_smoke.py; phase3_smoke.py; smoke.py | Production-proxy integration and accurate landing assertions |
| .github/workflows/ci.yml | Compatibility suite in native and Compose test jobs |
| README.md; docs/compatibility-api.md; ADR 0010; canonical docs/pointers; this report | Setup, contract, lifecycle, security and actual verification record |

`artifacts/` contains local ignored verification logs/schema/screenshot rather than committed product assets. No dependency manifests, lockfiles or `.env` were changed for this phase.

## F. Git status

Changes remain uncommitted and unstaged on `main`. No commit or push was performed. No user data, database volume or existing migration was reset/deleted. The exact final file inventory is available from `git status --short --untracked-files=all`; the important groups are listed above. Baseline was clean, so this phase's diff is reviewable against `8738106`.

## G. Next phase readiness

The code provides the versioned product/evidence/equipment/rule/result foundation for subsequent work. Agree Phase 6 requirements before expanding it. Release prerequisites remain the Compose host network issue, hosted CI, verified production TLS/session/origin routing, private storage/scanner, shared abuse limits, retention/backup/restore, release artifact review and customer-specific evidence/equipment acceptance. Decide future supported physical properties and uncertainty/sampling policy with domain owners; hardware/safety validation requires a separate documented process. No Phase 6 code is included.
