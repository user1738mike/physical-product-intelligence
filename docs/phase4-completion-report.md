# Phase 4 completion report

Date: 2026-10-15, Africa/Nairobi. Repository: `C:\Users\HomePC\Desktop\Billion2\physical-product-intelligence`.

## 1. Actual initial repository state

Started on `main`, HEAD `c4d61b5` (authentication/organization implementation). The working tree already contained the complete **uncommitted Phase 3 increment from this chat**, including migrations 0002–0004, product workflows, tests, UI and documentation. These changes were preserved; this report does not attribute them to Phase 4 or describe the initial tree as clean. No root AGENTS.md existed; frontend/AGENTS.md required reading the installed Next.js guides, which was done. No established file storage, scanner, durable job queue or document-parser dependencies existed. Authentication/tenant/claim/history services were inspected before implementation. No blocking Phase 3 isolation defect was found. Baseline: **75 PostgreSQL backend tests, 22 frontend tests passed**.

No staging, commit, push, database reset, volume deletion or Phase 5 work was performed. Existing databases, migrations and prior work remain. Temporary fixture accounts/jobs/files are retained in the disposable verification database/private fixture storage.

## 2. Implemented ingestion functionality

Private authenticated uploads; persistent tenant-scoped jobs; preview/validation; sheet/header/delimiter options; explicit column mapping; deterministic CSV/XLSX and labeled PDF/TXT adapters; per-attribute candidates; existing/competing-value comparison; corrections and append-only decisions; explicit new-product permission; owner/admin approval/rejection/selection; transactional retry-safe application; cancellation; refreshed comparisons invalidating prior approvals; job/row/candidate/history pagination; authorized original-source/error-report downloads; source checksum verification; existing product Evidence/revision/claim integration. No source value reaches canonical data while parsing or processing candidates.

The frontend supplies an organization import list/upload wizard, preview/mapping forms, job status/counters/errors, row creation permissions, candidate filters/comparisons/corrections/decisions, explicit measurement-selection checkbox, application/refresh/cancel actions, result product links and review history. Product evidence now links its private captured source and computed checksum.

## 3. Supported formats and configured limits

CSV: UTF-8/BOM and BOM-marked UTF-16, strict quoting, explicit or safe detected delimiter, duplicate/empty header rejection, row-width errors and empty-row/cell handling. XLSX: read-only selected sheet/header, bounded ZIP/XML expansion and relationships, no formulas/macros/external objects. PDF/TXT: bounded, deterministic anchored labels, one product per page, source page retained; text PDFs only. Unknown fields/values are never fabricated, and units are never inferred.

Default limits: 2 MiB/file, proxy 3 MiB multipart envelope only on the import collection, 200 data rows, 32 columns, 5 sheets, 10 PDF pages, 2,000 characters/cell, 500,000 extracted characters, 128 archive entries, 8 MiB expanded workbook, compression ratio 100, 20-second parser wall timeout. Linux adds hard 512 MiB address space and 10 CPU seconds. Windows does not have that Linux hard memory limit. Streaming Django upload handling stops oversized file bytes before downstream memory/temp handlers persist the excess. Organization bounds: 20 unfinished jobs and 100 MiB retained source bytes; best-effort import throttle 120/hour/user. Existing product precision/provenance/claim/source-count limits still apply.

Limits are configurable in `INGESTION_LIMITS`, with environment overrides documented in the [operating guide](ingestion-api.md). Unsupported: DOC/DOCX, XLS/XLSM, encrypted/malformed documents, arbitrary PDF prose/tables/layouts, scans/OCR, model extraction, URL fetching and AI vision. Formula cells are visibly unsupported, not evaluated or replaced by cached results.

## 4. Models, migrations, endpoints and screens

New `ingestion` app: ImportJob (tenant/file checksum/private key/status/version/options/mapping/preview/counters), ImportRow (raw source/location/scoped targets/revision and packaging versions/results), Candidate (raw/proposed/normalized field/comparison/quality/decision/reviewer/result claim), ReviewRecord (append-only mapping/correction/decision/creation record with actor/time/reason and before/after). Existing product Evidence is reused. No competing product provenance or audit model was introduced.

One additive migration, `ingestion/0001_initial`, depends on preserved products/0004. It adds four tables, organization/status index, per-job row/per-row field uniqueness and status/decision/quality checks. Existing migrations were not changed. Ordinary customer APIs do not edit raw uploads/rows or delete review/evidence history. Trusted DB/storage operators remain privileged; no new RLS or DB-level history immutability is claimed.

API root `/api/v1/organizations/{organization_id}/imports/`: collection GET/POST, limits GET, job GET, validate/mapping/process/apply/refresh/cancel POST, rows/candidates/history GET, candidate review POST, row creation permission POST, file/errors GET. Routes use strict serializers, bounded queries and existing session/CSRF/tenant authorization. Product evidence gains nullable source_artifact and conditional stored_private capture status. Detailed payloads/status codes are in [ingestion API](ingestion-api.md); OpenAPI is generated/validated from real serializers.

Screens: `/organizations/[organizationId]/imports` and `/organizations/[organizationId]/imports/[jobId]`. Imports navigation is in the existing tenant frame; availability text now accurately distinguishes imports from deferred assessments. Typed multipart requests reuse fresh CSRF and preserve browser multipart boundaries. The proxy preserves attachment/nosniff/sandbox headers and its original smaller JSON-body limit.

## 5. Provenance and conflict-resolution semantics

Jobs retain original private bytes, server-computed SHA-256, parser version and options. Rows/candidates retain source values/location, canonical normalization, comparisons, corrections and decisions. Applied rows create existing Evidence records and immutable source-linked product snapshots; old source sets are not edited. Product evidence exposes an authorized relative download path, never an internal key/path or public bucket URL. Digests verify byte identity, not supplier authenticity, rights or real-world measurements. Upload/transcription timestamps are explicitly identified when source measurement dates are unknown.

New/equivalent/duplicate/conflict/invalid are distinct. Decimal-normalized metric equivalence avoids false unit conflicts. Package candidates compare with their intended package, not the product-level mass. Different measurements stay separate; selecting one is optional, explicit and requires owner/admin rationale. All accepted claims are recorded before applying the selection so row order does not invalidate a deliberate batch decision. Conflicting approved descriptors or distinct canonical selections abort instead of silently choosing a last row. Empty cells do not erase catalog values. Duplicate mapped rows remain traceable and must be rejected.

Approval creates **reported** claims, never physically verified measurements or ClaimVerification. Existing measured/estimated observations remain immutable. New-product creation additionally needs row permission and an approved name; package-scoped rows need package_name approval, with package_type for a new package. All candidate decisions must be made before application. Entire approved application, result links, counters and success audit records commit together. Explicit rejections/invalid rows can yield completed_with_errors with actual results; unexpected failures roll back everything. Changed products/packages/claim comparisons require refresh and renewed approval. Repeated review/apply is idempotent; repeated completed-job apply returns its existing result. Separate identical uploads only produce warnings and still require independent review.

## 6. Tenant isolation and upload security results

All members upload, validate/map/process and inspect their active organization's jobs/results/source files. Only owner/admin correct/approve/reject, authorize new creation, select canonical measurements, cancel/refresh or apply. Every operation reuses current membership and organization locks; staff has no bypass. SKU targets are resolved inside the authorized tenant. Client-supplied product/organization IDs, actor/status/verification fields and arbitrary mapping/query fields are rejected. Nested candidate/row references are constrained to their authorized job.

PostgreSQL tests cover anonymous/session-CSRF upload rejection; cross-tenant jobs/files/candidates/errors/history/mutations; wrong nested job IDs; member approval denial; revocation/suspension; extension/MIME/magic/encoding/size/path checks; streaming size handling; malformed/encrypted PDF/XLSX; ZIP entry/expansion/sheet constraints and formulas; CSV BOM/quoting/delimiters/headers/row errors; PDF/TXT source locations; invalid units; normalized equivalent and competing values; corrections/rejections/history; no parsing-time catalog writes; source integrity; rollback; stale targets; duplicate rows; repeated and concurrent apply.

Browser checks exercised real production upload/file chooser, preview, confirmed mappings, candidate generation, explicit creation permission, invalid-zero rejection with focused alert, reported mass selection, descriptor approvals, transactional completion and resulting catalog/evidence/private-source link. The synthetic import created one product, one packaging configuration and one reported mass claim. A final member browser session could read an awaiting-review job and candidates/history with zero approval, creation or apply controls. Completion counters distinguish unresolved numeric conflicts after selection from detected candidate conflicts. Screenshot: ignored `artifacts/phase4-import-completed.png` (final production styling). Functional browser review is not formal WCAG certification or a complete mobile/device matrix.

## 7. Actual executed checks and results

| Executed check | Result |
| --- | --- |
| Initial git/docs/models/services/auth/dependency inspection | Existing uncommitted Phase 3 preserved; no background/storage/parser infrastructure |
| Baseline backend PostgreSQL / frontend suites | 75 / 22 passed |
| Full Phase 1–4 PostgreSQL suite | **98 passed**; `artifacts/phase4-final-complete-tests.log` |
| Final ingestion suite after scope/comparison/revalidation refinements | **23 passed**; `artifacts/phase4-final-ingestion-tests.log` |
| Additional focused revalidation/streaming/correction checks | Passed: 2 revalidation checks, 2 streaming/correction checks and 2 final conflict-summary/upload checks; corresponding artifacts logs retained |
| Frontend suite | **26 passed** in six files; includes multipart CSRF, isolated body allowance, private binary headers and review transport |
| Ruff check / format | Passed on backend/scripts; 70 Python files after streaming handler |
| Frontend lint/typecheck | Passed |
| Frontend format and final production build | Passed: final Prettier check and standalone production build; import list/detail routes included |
| Native migration/system/drift/OpenAPI checks | Passed; additive ingestion migration applied; no schema warnings |
| Combined Phase 3/4 production proxy smoke | Passed upload >64 KiB, CSRF, mapping, private exact bytes, review roles, provenance, explicit selection, idempotent apply, nested tenant denial, catalog/auth regression |
| Phase 2 final proxy/auth smoke | Passed: 200 reads, session cookies/login/logout/replay, CSRF/origin denial, tenant/role denial and revocation |
| Existing setup regression tests | 4 passed after rerunning outside the Windows temporary-directory sandbox restriction |
| Python dependency consistency | `pip check`: no broken requirements |
| Compose build/start attempt | Both application images built; network allocation failed, see section 8 |
| Browser workflow | Actual upload → completion → resulting product/private evidence link passed; focused zero-value rejection verified |
| Final diff/whitespace/staging review | Passed: no whitespace errors, staging/commit/push or tracked .env change; exact final status below |

During verification, a test assuming the attribute-list order was corrected to find mass by name. A final Windows build initially failed because this task's running standalone server held its directory; the owned process was stopped before rebuilding. Prettier also reported one newly added test; it was formatted. These failures were not suppressed or represented as passing runs. Later successful outcomes are recorded above. No authentication/tenant tests were weakened; the landing disclosure assertion was updated for newly available imports.

## 8. Database, Docker and CI status

Native PostgreSQL 16.13 on loopback 55432: ingestion migration applied to the dedicated `ppi_phase2_verification` database. Before/after counts of all existing business records matched: users 18, organizations 17, memberships 19, audit events 323, products 35, evidence 14, product revisions 47, revision-source links 4, bundled profiles 8, measurements 4, live packaging 4, configuration history 16, claims 16, verification 4 and selection 4. Django legitimately added 4 content types and 16 permissions; a broad count-equality assertion initially flagged that expected metadata growth. No existing record was deleted/reset; later smoke/browser fixtures intentionally increase counts.

`docker compose up --build -d` built both application images but failed creating `physical-product-intelligence_default`: **all predefined address pools have been fully subnetted**. Final `docker compose ps -a` was empty. No networks/volumes were pruned or deleted, and no workaround subnet or unrelated-project change was made. Compose PostgreSQL 17.11 runtime is unverified; native PostgreSQL passing tests are not claimed as container acceptance. A cached backend rebuild also passed with the ingestion security refinements. The source checks/native runtime, not an immutable released container digest, are the acceptance evidence; the last schema annotation and summary-counter refinements have focused tests rather than a released container digest.

CI now explicitly includes ingestion tests; the existing Phase 3 smoke invokes Phase 4 coverage using its same two accounts, avoiding an extra signup-throttle batch. CI shutdown preserves volumes. **Hosted CI was not run** because no commit/push was requested. Real production TLS/ingress, scanner, object store and durable worker behavior were not verified. Temporary loopback servers were used only against the disposable database and are stopped after verification; the pre-existing PostgreSQL and port-8000 listener are preserved.

## 9. Dependencies

Pinned additions to requirements.in/lock: openpyxl 3.1.5 (read-only XLSX), et_xmlfile 2.0.0 (its dependency), defusedxml 0.7.1 (hardened XML), pypdf 6.20.1 (text-PDF extraction). Registry versions and primary-library security/extraction guidance were checked. No cloud SDK, OCR engine, model API, paid service/key, Redis/Celery or frontend dependency was added. Installation used the existing project virtual environment. Dependencies and native parsers still require operational patch review and isolation; limits are not a complete malware defense.

## 10. Files changed and final Git status

Phase 4 adds backend/ingestion (models, migration, storage/streaming uploads, parser adapters/worker, services, strict serializers, views/routes/tests), frontend/lib/ingestion.ts, frontend/app/imports/workspace.tsx, two organization import route wrappers, frontend/tests/ingestion.test.ts, scripts/phase4_smoke.py, ADR 0009, ingestion guide and this report. It extends backend settings/URLs/dependency pins/product source serialization, frontend transport/proxy/navigation/provenance/availability/styles, existing smoke/disclosure assertion, CI and requested canonical/nested documentation. All prior Phase 3 work remains in the same unstaged tree.

```text
 M .github/workflows/ci.yml
 M README.md
 M backend/config/settings/base.py
 M backend/config/settings/development.py
 M backend/config/settings/test.py
 M backend/config/urls.py
 M backend/products/admin.py
 M backend/products/models.py
 M backend/products/serializers.py
 M backend/products/services.py
 M backend/products/tests.py
 M backend/products/urls.py
 M backend/products/views.py
 M backend/requirements.in
 M backend/requirements.lock
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
 M frontend/app/api/v1/[...path]/route.ts
 M frontend/app/globals.css
 M frontend/app/page.tsx
 M frontend/lib/api.ts
 M frontend/tests/foundation.test.tsx
 M frontend/tsconfig.json
 M scripts/phase3_smoke.py
 M scripts/smoke.py
?? backend/ingestion/__init__.py
?? backend/ingestion/migrations/0001_initial.py
?? backend/ingestion/migrations/__init__.py
?? backend/ingestion/models.py
?? backend/ingestion/parsers.py
?? backend/ingestion/serializers.py
?? backend/ingestion/services.py
?? backend/ingestion/storage.py
?? backend/ingestion/tests.py
?? backend/ingestion/uploads.py
?? backend/ingestion/urls.py
?? backend/ingestion/views.py
?? backend/ingestion/worker.py
?? backend/products/migrations/0002_catalog_workflows_and_attribute_claims.py
?? backend/products/migrations/0003_postgres_provenance_guards.py
?? backend/products/migrations/0004_finite_physical_values.py
?? backend/products/test_workflows.py
?? backend/products/workflow_serializers.py
?? backend/products/workflow_views.py
?? backend/products/workflows.py
?? docs/architecture-decisions/0008-catalog-workflows-and-attribute-verification.md
?? docs/architecture-decisions/0009-bounded-reviewable-ingestion.md
?? docs/architecture/system-architecture.md
?? docs/ingestion-api.md
?? docs/phase3-completion-report.md
?? docs/phase4-completion-report.md
?? docs/product/product-requirements.md
?? docs/security/threat-model.md
?? frontend/.prettierrc.json
?? frontend/AGENTS.md
?? frontend/app/imports/workspace.tsx
?? frontend/app/organizations/[organizationId]/imports/[jobId]/page.tsx
?? frontend/app/organizations/[organizationId]/imports/page.tsx
?? frontend/app/organizations/[organizationId]/products/[productId]/edit/page.tsx
?? frontend/app/organizations/[organizationId]/products/[productId]/page.tsx
?? frontend/app/organizations/[organizationId]/products/new/page.tsx
?? frontend/app/organizations/[organizationId]/products/page.tsx
?? frontend/app/products/catalog.tsx
?? frontend/app/products/detail.tsx
?? frontend/app/products/evidence.tsx
?? frontend/app/products/page.tsx
?? frontend/app/products/ui.tsx
?? frontend/lib/ingestion.ts
?? frontend/lib/products.ts
?? frontend/tests/ingestion.test.ts
?? frontend/tests/products.test.tsx
?? scripts/phase4_smoke.py
```

## 11. Known limits and deferred production requirements

- Production uploads/sources require a configured trusted malware scanner; no engine is bundled. Development fixtures are visibly unscanned.
- Private object-storage deployment, encryption/keys, bounded durable quarantine/scanner workflow, no-egress isolated workers, queue recovery, distributed ingress/abuse limits, backups, retention/legal hold and orphan reconciliation remain deployment work. Default private local storage requires appropriate volume access/backup policy.
- Synchronous parsing/application is bounded for development-sized imports. Transient validating/processing states are inside transactions and not reliable live-progress polling signals. Windows lacks Linux's hard memory/CPU enforcement. Scanner hooks must be independently time/resource bounded.
- Narrow labeled PDF/TXT extraction only; no OCR, arbitrary layouts, AI provider, URL fetch, DOC/DOCX, XLS/XLSM or general workflow designer. Job-specific mappings only; no reusable mapping presets.
- Approved text updates editorial catalog values; measurements become reported claims with separate optional selection. Integrity/approval is not supplier authenticity, rights verification, physical truth or safety certification.
- Existing catalog source/claim caps may reject imports atomically; larger import performance/load review and streaming/object-store release tests remain open.
- Docker runtime/hosted CI/real HTTPS and independent accessibility/security release review remain unexecuted. No Phase 5 compatibility work, commit or push.

## 12. Exact setup and testing commands

From repository root, normal disposable Compose development once host networking is repaired:

```powershell
python scripts/setup_env.py
docker compose config --quiet
docker compose up --build --wait --wait-timeout 240
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test accounts organizations operations products ingestion --settings=config.settings.test
docker compose exec -T backend python manage.py spectacular --validate --fail-on-warn --file /tmp/openapi.yaml
python scripts/phase2_smoke.py --allow-create-test-data --read-cycles 50
python scripts/phase3_smoke.py --allow-create-test-data
python scripts/smoke.py
```

The Phase 3 command includes Phase 4 smoke. Smokes intentionally create retained disposable users/tenants/jobs/uploads/products; never run them against customer data. Setup preserves existing .env. Stop Compose with `docker compose down` without volume deletion.

Native backend checks used the already-running isolated PostgreSQL cluster:

```powershell
$env:DJANGO_SETTINGS_MODULE='config.settings.test'
$env:POSTGRES_HOST='127.0.0.1'
$env:POSTGRES_PORT='55432'
$env:POSTGRES_USER='ppi'
$env:POSTGRES_DB='ppi'
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py test accounts organizations operations products ingestion --keepdb --verbosity 0
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py spectacular --validate --fail-on-warn --file artifacts/openapi-phase4.yaml
.\.venv\Scripts\ruff.exe check backend scripts
.\.venv\Scripts\ruff.exe format --check backend scripts
```

For native HTTP/browser use a separate terminal with the same isolated host/port/user, but `DJANGO_SETTINGS_MODULE=config.settings.development` and `POSTGRES_DB=ppi_phase2_verification`; run migration and `python backend/manage.py runserver 127.0.0.1:8001 --noreload`. From frontend:

```powershell
npm.cmd run format:check
npm.cmd run lint
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
New-Item -ItemType Directory -Force .next/standalone/.next/static | Out-Null
Copy-Item -Path .next/static/* -Destination .next/standalone/.next/static -Recurse -Force
$env:API_BACKEND_ORIGIN='http://127.0.0.1:8001'
$env:HOSTNAME='127.0.0.1'
$env:PORT='3000'
npm.cmd run start
```

Stop the owned standalone server before rebuilding on Windows. Sign in at `/account`, choose an organization via `/products`, then Imports. Production uses deployment settings with private storage and INGESTION_SCANNER; development permission for unscanned fixtures is not a production credential/scanner workaround. See the operating guide for exact format/limit/configuration semantics.

## 13. Phase 4 acceptance checklist

- [x] Existing work/auth/tenant/product provenance inspected and preserved; baselines run.
- [x] Private tenant-scoped uploads, opaque keys, streaming/type/format/size/resource bounds and safe errors.
- [x] CSV/XLSX explicit field mapping and row validation; formula/macro execution excluded.
- [x] Supported deterministic PDF/TXT extraction yields source-located candidates with explicit unknowns/units.
- [x] Per-attribute provenance, competing/equivalent/invalid distinctions and original correction/rejection history.
- [x] Owner/admin approval, explicit new-product permission and optional canonical selection; no physical promotion.
- [x] Transactional retry-safe application, stale-target checks and concurrent apply coverage.
- [x] Two-tenant jobs/files/rows/candidates/reviews/results/report isolation and role tests.
- [x] Real frontend/API upload-to-completion flow; result private-source link and invalid-input focus verified.
- [x] Existing Phase 1–3 backend regression suite passes; new migration preserves business records.
- [x] API schema, tests, documentation and CI configuration updated.
- [ ] Compose PostgreSQL 17.11 runtime — host address-pool exhaustion.
- [ ] Hosted CI, production scanner/object storage/durable isolation/TLS, load and independent release audits — deployment-dependent/unexecuted.

No Phase 5, commit or push was performed.
