# Phase 9A — Commercial foundation completion

2026-10-16. **Local feature checks complete. Hosted/staging/production acceptance remains blocked.** No payment integration is claimed.

## A. Baseline audit

Started clean at `854351c12b0c25d5832f138989de6f0a71f70461`, published `codex/phase8b-release-gates`. Created local `codex/phase9a-commercial-foundation`; no stage/commit/push. Read frontend AGENTS and installed Next server/client/routing guides, roadmap, Phase 8B report/handoff, organization authorization/audit, product/import/assessment services, AI lease lifecycle, migrations, role tests and existing browser runner. Phase 8B's 202 backend/37 frontend/15 script/18 evaluation results are historical, superseded only by the new checks below. The historical dirty-build manifest remains unchanged.

## B. Implemented behavior

New `backend/commercial` models/services/API/operator commands and six additive migrations implement immutable plan versions, non-overlapping assignments, unlimited pilot enrollment/backfill, centralized feature/capacity policy, monthly reservations, immutable usage/adjustments and decision/operator histories. Existing organization creation enrolls atomically. Product/reactivation/import creation, catalog mutations, equipment/rules, assessments and both extraction paths call the central service. Existing authorization, provider configuration and deterministic/human-review semantics remain mandatory.

Added typed frontend transport and organization Plan and usage route/navigation, useful denial messages with preserved machine codes, and owner/admin read-only allowances/history. CI includes commercial in both explicit backend lists and expanded real-browser coverage. Scanner tooling can inventory the selected candidate SDK image instead of assuming Phase 8's tag. Deployment grants, schema, roadmap, API and operations documentation were updated.

## C. Contract and invariants

See [API/permission matrix](commercial-api.md) and [operator/recovery procedures](commercial-operations.md). Members cannot read commercial data; foreign/revoked membership is 404, with no staff shortcut. Policy has five typed boolean features and three nullable nonnegative quota limits. Pilot preserves functionality; missing policy fails closed. Current active products are capacity. Assessments count committed results. Extraction counts completed candidate generation independently of candidate count or subsequent review/application; provider failures do not count.

UTC months have exclusive ends and are pinned at first processing admission. Replacement does not reset totals. Organization locks serialize admission; operation identity/digest prevents double counting or changed-input reuse. Durable AI reservations use existing lease fencing; recovery changes job state before releasing capacity. Immutable decision events preserve retry policy versions. PostgreSQL exclusion constraints, append-only/scope/operator triggers and deferred reservation/usage pairing backstop application services. Historical reads and authorized cleanup remain available after quota exhaustion or commercial expiry/suspension. Conflicting future assignments require deliberate operator handling rather than automatic rewriting.

## D. Verification

| Check | Classification and actual evidence |
| --- | --- |
| Complete backend/PostgreSQL | **Executed/passed: 228 tests, zero skips, 161.838s**, new SDK image, isolated `test_ppi_phase9a_validation` on PostgreSQL 17. `artifacts/phase9a-backend-final.log`. Includes 26 commercial tests: real concurrent last-product/last-reservation admission and duplicate completion; exact assessment idempotency/rollback, mocked extraction failure/cancel/recovery/late-worker fencing, bulk-import all-or-nothing capacity, raw SQL constraints, runtime role denials and enrollment/backfill idempotency. |
| Frontend | **Executed/passed: 42 tests/9 files**, format, lint, type generation/check and webpack production build. `artifacts/phase9a-offline-frontend-final.log`. New tests cover unlimited/zero/expired/suspended/unassigned states and tenant-keyed no-store/error transport. |
| Backend consistency/schema | **Executed/passed:** pip check, Django check, migration drift check, applied migration check, spectacular validation; `artifacts/phase9a-backend-checks-final.log`. Initial validation container omitted required storage configuration and failed; corrected explicit storage/scanner settings passed. |
| Extraction evaluations | **Executed/passed: 18/18, provider_calls 0**. Inert provider check reports not executed because explicit live authorization is absent. No live request. |
| Scripts/style/config | **Executed/passed: 15 script tests**, synthetic production-config check, Ruff check/format (148 Python files), owned browser JS/JSON Prettier and JS syntax; workflow parsed with six job definitions and explicit commercial tests. Official vendor seccomp file is intentionally preserved byte-for-byte rather than reformatted. |
| HTTPS business smoke | **Executed/passed:** phase2/3 smoke against port 19443 with recorded fixtures, covering sessions/CSRF/cookies, 200 repeated reads, catalog/import/assessment/review/source scanning and tenant/role denials. `artifacts/phase9a-smoke.log`. |
| Real Chromium | **Executed/passed: one full journey, nine checkpoints, 59.6s**, private-CA validation and sandbox enabled, Playwright 1.64.1. `artifacts/phase9a-browser-final/{acceptance,execution,browser}.json`, sanitized log and historical-assessment screenshot. Covers usage counts (four assessments/one extraction), owner/admin/member/revoked access, finite capacity error, expiry/suspension and switching back to unlimited pilot. Earlier run correctly displayed capacity denial but its assertion also matched Next's hidden announcer; scoped locator fix passed. |
| Standard Docker recipes | **Executed/failed:** registry metadata TLS timeouts for Python/Playwright and 401 for Node; sanitized `phase9a-build-*.log`. No unchanged retry loop, credentials change or TLS bypass. |
| Offline builds | **Executed/passed:** network-disabled local builds from exact preserved Phase 8 runtime/SDK/browser images and verified frontend development dependencies. Backend source is copied into the existing immutable runtime bases. Frontend reruns all checks/build, then runs new standalone output under `/release` in the prior production base. Recipes/logs are in ignored `artifacts/phase9a-*-offline.Dockerfile` and `phase9a-offline-*.log`. These are new local verification artifacts, not a passing standard hosted build. Initial frontend test import alias failed; repository-style relative imports fixed it. |
| Image vulnerability acceptance | **Blocked:** new seven-image inventory in `artifacts/phase9a-scans/summary.json` refuses invalid/missing Grype DB with auto-update disabled. No DB download retried, no zero-finding claim. Existing frontend advisory result applies only to its unchanged dependency lock; new image acceptance remains required. |
| Hosted CI | **Blocked/unexecuted for dirty Phase 9A source.** Latest published SHA remains Phase 8B; its exact run 38924216661 was prevented from starting all nine jobs by account billing. No account settings changed. |
| Actual staging/public TLS | **Blocked:** no approved target/domain/region/budget or deployment authorization. |

Backend command: `docker run --rm --network ppi-rehearsal-1685df9267_default --env-file artifacts/phase8-final/migration.env -e POSTGRES_DB=ppi_phase9a_validation -e DJANGO_SETTINGS_MODULE=config.settings.test -e INGESTION_SCANNER= -e TRUSTED_PROXY_CIDRS= -v ppi-rehearsal-1685df9267_rehearsal_tls:/certs:ro --entrypoint python ppi-phase9a-backend-sdk manage.py test accounts organizations operations products ingestion compatibility commercial --noinput`.

Browser command: `.venv/Scripts/python.exe scripts/browser_acceptance.py --directory artifacts/phase9a-rehearsal --output artifacts/phase9a-browser-final --commercial-fixtures`. The fixture command is restricted to explicit synthetic rehearsal settings/database identity and uses a new synthetic operator; it does not expose a privileged web endpoint.

New exact local artifacts: backend `sha256:9a36cbcb3a120842dd39cc75be737480705f04b28847f931861fd10cd209d9fc`; SDK `sha256:0c83a332de4a1b8b1ce34aad665524ea373028d2277bad090861de5b38873077`; frontend `sha256:9bef7aa53aefde4d1594c45ea8bff5398a8f143b160df7d971c3188f6e47e94f`; final browser `sha256:5a30077a7c8a6b4d76ee35861037af931235b98a73856cda8adc1e26218b5f71`. Source/evidence receipts are recorded separately in ignored artifacts, not substituted into historical manifests.

## E. Migration and runtime roles

Fresh isolated rehearsal `ppi-rehearsal-adb8f69298`, database `ppi_rehearsal_adb8f69298`, URL `https://127.0.0.1:19443` applied all migrations and actual narrowed non-owner grants. Its browser/API workflow confirms runtime enrollment, reservations and ledger writes. PostgreSQL role tests also exercised broad DML with guards intact, rejecting assignment/ledger/account rewrites and operator invocation. Backfill preserves existing assignments and records the metering start; no historical usage was fabricated. Upgrade of an actual staging/customer database is **documented/not executed**. Preserve backups and test exact staging-role grants before promotion.

## F. Gaps and release blockers

No prices, payment provider, checkout, recurring collection, invoices, overages or payment success is implemented. Scheduled conflicting assignments are rejected; no automatic future-schedule cancellation/rewriting is offered. Real public TLS, standard hosted builds, acceptable Grype scans, hosted exact-candidate CI, staging/monitoring/recovery acceptance remain open. The Phase 8B host handoff remains a recipe, not allocated infrastructure.

## G. Git and external actions

All Phase 9A implementation remains local and uncommitted on `codex/phase9a-commercial-foundation`, based on the published Phase 8B SHA. No stage/commit/push/merge, image publication, remote deployment, billing/DNS/secret change, purchase or live AI/payment call. Root `.env` remains 475 bytes with its original October 14 timestamp. Existing DBs/private files/volumes and unrelated applications were preserved; only new synthetic data, test databases and local validation artifacts were created. Registry metadata requests failed as documented; verification builds used local immutable bases without network access.

## H. Readiness and next increment

**Local commercial foundation complete; exact-candidate hosted acceptance not passed; staging not validated; production release blocked.** Phase 9B must audit this actual boundary and preserve its uncommitted source/evidence before adding billing. A real payment increment needs explicit provider/merchant ownership, supported currency/prices and commercial policy, verified event/settlement/access rules, sandbox authorization and eventual release gates. No provider selection or live collection is implied by this report.
