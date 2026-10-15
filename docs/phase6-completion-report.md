# Phase 6 completion report

Date: 2026-10-15. Scope: optional AI-assisted product specification extraction, source-grounded validation and human review. No Phase 7 implementation or live model request.

## A. Audit

The actual tree already contained Phase 2 identity/tenancy/session/CSRF/audit, Phase 3 product/package/evidence/claim/history workflows, Phase 4 private bounded ingestion/candidates/review/application and Phase 5 immutable equipment/rules/assessments. Phase 5 was **uncommitted and unstaged** on `main` at `8738106`, including untracked compatibility files. Those changes were preserved and extended, not reset, staged or replaced. Models, services, migrations, routes, frontend, settings, locks, CI, Phase 5 report and compatibility guide were inspected. No previous AI provider integration or installed OpenAI SDK existed.

Existing ImportJob, ImportRow, Candidate, immutable ReviewRecord, evidence/claim/selection services and assessment provenance were suitable. No material tenancy/evidence/immutability blocker or prerequisite rewrite was found. The existing frontend baseline passed 32 tests. An initial PostgreSQL baseline attempt encountered an already-existing `test_ppi` database and stopped at Django's interactive creation prompt; it was not deleted/reset. A separate isolated `test_ppi_phase6` test database was subsequently created/preserved with `--keepdb`, and the complete suite verified Phase 2–6 together.

The user explicitly authorized reuse of the existing secure OPENAI_API_KEY, prohibited revealing/copying/logging/committing it and prohibited live API checks without separate authorization. No key was created, copied to a file, displayed or used for a live request. AI remains disabled by default, including the native verification server and CI.

Packaging review additionally found that the backend Docker context did not exclude local private media. The minimal repair adds `media` to `backend/.dockerignore`; the final image is rebuilt and checked offline for its absence. No private upload or prior local Docker cache was deleted, and no image was published.

## B. Implementation

### Persistence and lifecycle

ImportJob gains mode (`deterministic`/`ai`), protected original source, tenant/request UUID uniqueness and extraction metadata. Candidate gains extraction provenance. No duplicate evidence, candidate, review or assessment model is introduced. Migration `ingestion.0002_candidate_extraction_importjob_extraction_and_more` is additive; `0003_extraction_scope_guards` adds reversible PostgreSQL deferred source and target integrity guards. Existing rows default to deterministic mode. Jobs reference existing private bytes rather than copying them, and upload quota counts original files once.

Queueing captures explicit existing product/package targets without contacting a provider. Uploaded/queued → processing lease → awaiting review → reviewed atomic application (completed/completed with errors). Failed and cancelled states retain meaningful fixed diagnostics. Explicit retry is allowed only for transient errors, at most three attempts. No SDK auto-retry, new queue, autonomous agent or background infrastructure is added. One fresh processing lease per tenant bounds concurrency; after 90 seconds an authorized reviewer may recover an interrupted lease. Lease matching prevents duplicate persistence and late cancelled results. Database locks are released during external work and authority/source/targets are checked again on finish.

### Provider and validation

A small ExtractionProvider protocol and one configurable **optional** OpenAI SDK 3.31.0 adapter use Responses strict JSON Schema, no tools, fixed official origin, requested `store=false`, 8-second request timeout and 2,500 output-token bound. Credentials are accessed only in the backend environment. Availability is checked without SDK construction/network access. Optional `requirements-ai.in`/`requirements-ai.lock`, Docker build argument and Compose settings support deployment without making the SDK/core AI availability mandatory. Core dependency locks are unchanged.

Application-owned `grounded-spec-v1` schema allows only length/width/height/mass and product name/brand/manufacturer/description. The provider supplies no tenant/evidence/verification authority or normalized values. Exact supplied segment/quote/original support and literal numeric value-unit pairing are validated before deterministic existing Decimal normalization. Invalid JSON/envelopes fail the job; malformed/unsupported/unknown/ungrounded items are preserved for rejection/manual review. Original source text, original units, canonical operands, source checksum/location, method/model/schema/time, validation and decision history remain distinct. Unknowns never become guessed measurements. Confidence is null, never an authority score.

PDF/TXT gain bounded plain-text segmentation alongside existing deterministic labeled parsing. CSV/XLSX reuse hardened parser rows/options. Source limits: 24,000 text characters, 80 segments, 30 candidates, 24,000 accepted output bytes, existing file/page/archive/process bounds and 20 unfinished imports. AI start/process endpoints use best-effort 20/hour per-process throttling. No silent truncation, OCR, arbitrary binary or URL fetching is added. Exact textual support does not prove semantic correctness or manufacturer authenticity.

### Review, APIs and UI

Existing review/correct/reject/select/apply/history endpoints handle AI candidates. Source and tenant integrity are rechecked; normalization is revalidated on application. Optimistic versions and identical-request retries preserve individual decision histories. Conflicting, duplicate and equivalent assertions remain separate. Human approval records acceptance for application; explicit numeric canonical selection is separate. Approved source assertions become **reported**, never physically measured claims. New contradictions/stale targets require refreshed comparisons and renewed review. Transaction failure cannot leave partial claims or falsely completed jobs.

New API paths beneath the existing organization imports root: `ai-capabilities/`, `{source}/extractions/`, `{job}/ai-process/` and candidate detail. Existing job/list/filter/review/refresh/apply/cancel/history/private source paths are reused. Owner/admin controls extraction/review/application; all current active members may read. Cross-tenant nesting, missing membership, CSRF and staff-bypass attempts retain existing denial conventions. AI jobs reject deterministic process/mapping routes and vice versa. Client model/URL/key/evidence/verified fields are rejected.

Next.js adds availability/privacy messaging, searchable paginated target selection, existing packaging selection, explicit queue/process/retry/cancel and provenance/excerpt display within Imports. Candidate reviews retain existing versioned forms, reasons and source access. Unknown/ungrounded approval is disabled/defaults to reject in the final form; server validation remains authoritative. Original AI source values avoid duplicated units, and normalized values display readable original-to-canonical operands. Loading/errors/roles/partial-success states use the existing design system.

Phase 5's deterministic evaluator is unchanged. Evidence snapshot serialization now retains extraction provenance so new assessments preserve model/schema/source excerpt along with claims. Extraction code cannot alter or activate rules, evaluate compatibility or rewrite old assessments. An integration test establishes a new reliable mass failure only after human review/application and an explicit new deterministic assessment, while prior snapshots and rule definitions remain unchanged.

## C. Verification

| Check | Actual result |
| --- | --- |
| Final complete native PostgreSQL suite | **166 passed**, including 34 Phase 6 tests; `Ran 166 tests in 136.945s`, OK |
| Frontend | **37 passed**, eight files |
| Setup regression | **4 passed** |
| Ruff lint / format | Passed; 90 Python files formatted |
| Python dependency consistency | No broken requirements |
| Django / migration drift | No issues / no changes detected |
| Applied migrations | Additive 0002/0003 applied; migrate check passed |
| Existing data preservation | All 29 registered model counts equal before/after |
| OpenAPI fail-on-warning | Passed after resolving candidate-detail operation-name collision |
| Frontend lint / typecheck / format | Passed |
| Production frontend build | Passed; existing tenant import routes include the new real UI |
| Catalog/ingestion/assessment/disabled-AI production proxy smoke | Passed |
| Browser review | Passed with explicitly labeled offline mocked fixtures |
| Optional SDK-enabled backend Docker build | Passed |
| Offline image packaging check | Passed in a network-disabled temporary container: SDK imports; no private media or env files |
| Compose configuration | Passed `config --quiet` |
| Compose runtime | Not rerun in Phase 6; prior host address-pool exhaustion remains unresolved |
| Hosted CI | Updated; not executed/pushed |
| Live provider integration / quality | **Not run**, explicitly prohibited without separate authorization |

Native PostgreSQL is the existing loopback cluster (16.13) on port 55432. Migrations used `ppi_phase2_verification`; test execution used isolated `test_ppi_phase6` with `--keepdb`. Migration counts are in `artifacts/phase6-migration-counts.json`: users 28, organizations 27, memberships 29, audit 624, products 46, claims 40, imports 8 and assessments 7 were among the preserved counts. No table/volume reset or existing record deletion occurred. Later disposable smoke/browser fixtures intentionally increase counts.

Key commands actually executed from repository root, using POSTGRES_HOST=127.0.0.1, POSTGRES_PORT=55432, POSTGRES_USER=ppi and test/development settings as appropriate:

```powershell
.\.venv\Scripts\python.exe backend/manage.py test accounts organizations operations products ingestion compatibility --settings=config.settings.test
.\.venv\Scripts\python.exe backend/manage.py makemigrations ingestion
.\.venv\Scripts\python.exe backend/manage.py test ingestion.test_ai --keepdb --noinput
.\.venv\Scripts\python.exe backend/manage.py test accounts organizations operations products ingestion compatibility --keepdb --noinput
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py spectacular --validate --fail-on-warn --file artifacts/openapi-phase6.yaml
.\.venv\Scripts\ruff.exe check backend scripts
.\.venv\Scripts\ruff.exe format --check backend scripts
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p test_setup_env.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip index versions openai --retries 0 --timeout 10
.\.venv\Scripts\python.exe -m pip install openai==3.31.0 --retries 0 --timeout 15 --report artifacts/phase6-sdk-install.json
.\.venv\Scripts\python.exe scripts/phase3_smoke.py --allow-create-test-data
docker compose config --quiet
docker build --build-arg INSTALL_AI=true -t ppi-backend-phase6-check ./backend
docker run --rm --network none ppi-backend-phase6-check python -c "from pathlib import Path; import openai; assert not Path('/app/media').exists(); assert not list(Path('/app').glob('.env*'))"
git diff --check
git status --short --untracked-files=all
git diff --cached --stat
```

The first test command stopped on the existing test database prompt; subsequent passing commands explicitly used the isolated keepdb test database. Migration application/count capture was an inline Python/Django script running `call_command('migrate', interactive=False)` and `call_command('migrate', check=True)` around all registered model counts. No secrets were printed. Initial SDK package lookup encountered sandbox DNS restrictions; the approved PyPI lookup/install succeeded. That package installation did not contact the OpenAI API.

From frontend: `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run format:check`, `npm.cmd run build` and static-copy for the native standalone server. Verification used hidden native Django port 8001 and Next.js production port 3000, with server-only API_BACKEND_ORIGIN=http://127.0.0.1:8001 and **AI_EXTRACTION_ENABLED=false**. Existing services/cluster were preserved. Optional SDK tests include a real SDK round trip through `httpx2.MockTransport`; even log entries naming the API URL in an early mock run represent an in-memory transport, not a live request. Final SDK/HTTP diagnostic suppression covers that logger namespace as well.

Test fixes were ordinary implementation corrections, not weakened security: PostgreSQL schema-editor escaping of `%ROWTYPE`, canonical decimal string precision in a test assertion, OpenAPI operation naming, numeric pairing boundaries, equivalent-unit candidate classification, mapped unknown-source locations and readable UI operands. The final full suite supersedes earlier diagnostic runs. No coverage percentage or hardware certification is claimed.

Evidence files: `artifacts/phase6-final-tests.log`, `phase6-proxy-smoke.log`, `phase6-migration-counts.json`, `openapi-phase6.yaml`, optional Docker build logs and browser fixture manifest/screenshots. Artifacts are ignored local verification evidence, not committed production assets. No hosted pipeline result is claimed merely because CI configuration exists.

### Browser verification

An existing synthetic local owner account opened `MOCKED-AI-NO-LIVE-CALL.txt`. Offline seeding used the actual ingestion services with a mocked provider and model label `MOCKED-OFFLINE-NO-API`; a guard prohibited the real adapter. The UI showed AI disabled, private source/checksum, three candidates, normalized reported mass/length and unresolved height. Mass was explicitly approved/selected, length approved, and attempted height approval was denied by the server with a focused error. Height was then rejected with a reason. Application completed honestly with errors: two approved, one rejected, two created reported claims, zero pending, with review history retained. No live extraction quality is implied. Browser evidence is labeled as offline mocked data.

The temporary browser tab and verified native frontend/backend processes were closed after final checks. Ports 3000/8001 no longer had verification listeners; PostgreSQL and unrelated services were preserved. Final screenshots are `artifacts/phase6-review.png` and `artifacts/phase6-candidate-review.png`.

## D. Security and privacy

Current membership/roles and same-tenant source/product/package/candidate scope remain server authority. Private file integrity/scanning and authenticated download controls are reused; source links grant no access themselves. New PostgreSQL source/target guards supplement transactional services, not RLS or privileged-operator tamper protection. Staff has no tenant bypass. Normal mutation payloads cannot choose model URLs, credentials, arbitrary fields or verified status.

Trusted instructions and untrusted source text are separated; the model receives no tools, shell/database/network authority or unrelated records. Quoted evidence/segment/value-unit checks and deterministic normalization are the primary machine safeguards, with explicit human approval/selection as the business boundary. Prompt injection, semantic mislabeling and false source claims cannot be eliminated by these checks. A malicious source can contain a plausible numeric claim, so exact citation is not a physical truth guarantee.

The adapter reads the existing key only for backend authentication. No new credential, secret file, browser key or secret-bearing log was created. Source text is sent only if an operator enables/configures the capability and an authorized user explicitly processes a queued job. Provider exception bodies and SDK wire diagnostics are not logged; bounded usage metadata has no claimed price. Requested storage off is not a substitute for reviewing provider retention, jurisdiction, contractual and customer-data policies. Production scanner/private storage, shared rate limits, worker supervision, ingress timeouts, retention/backups/restore and release artifact review remain requirements.

## E. Important Phase 6 files

| Paths | Purpose |
| --- | --- |
| backend/ingestion/ai_provider.py | Optional provider protocol/SDK, disabled states and sanitized error mapping |
| backend/ingestion/ai_schema.py | Strict response contract, quote/segment/literal pairing and bounds |
| backend/ingestion/ai_services.py | Explicit queue, retries, processing leases, cancellation-safe persistence/provenance |
| backend/ingestion/ai_views.py; urls.py | Capability/start/process/detail endpoints and OpenAPI |
| backend/ingestion/models.py; serializers.py; migrations/0002*; migrations/0003* | Reused job/candidate metadata, uniqueness and PostgreSQL reference guards |
| backend/ingestion/services.py; worker.py | Safe review/apply/refresh/cancel integration and bounded source segmentation |
| backend/products/serializers.py | Freeze extraction provenance into evidence/assessment snapshots |
| backend/ingestion/test_ai.py | 34 mocked schema/provider/security/review/concurrency/assessment tests |
| backend/requirements-ai.in; requirements-ai.lock; Dockerfile; .dockerignore; compose.yaml; .env.example | Optional pinned deployment, exclusion of private media and server-only configuration; existing .env unchanged |
| backend/config/settings/base.py | Disabled defaults, model/provider config and extraction throttle |
| frontend/app/imports/ai.tsx; workspace.tsx; frontend/lib/ingestion.ts | Real extraction selection/availability/review and provenance integration |
| frontend/tests/ai-extraction.test.tsx | Five new frontend tests for states, provenance, escaping and transport/errors |
| scripts/phase6_smoke.py; phase3_smoke.py; .github/workflows/ci.yml | Disabled-provider smoke, mocked CI extra and explicit no-live default |
| docs/ai-extraction-api.md; ADR 0011; README and canonical docs/pointers | Setup, privacy, contracts, limits and actual completion record |

The existing Phase 5 files remain uncommitted alongside these changes. The final Git diff against HEAD therefore includes both phases; the table above identifies Phase 6 responsibilities rather than falsely attributing every existing change to this phase.

## F. Limitations

No live API call or model quality/access/latency check was authorized or run. Operators must select a structured-output-capable model and review data policy before enabling; no model or paid call is required for startup/development/CI. The supported adapter is OpenAI only, replaceable via reviewed backend code. Three real-SDK tests skip when the optional SDK is absent; the native CI backend job installs it and runs all tests with mocks. Core-only Docker remains useful without it.

No OCR/images, new binary formats, arbitrary external sources, inferred manufacturer identity, new-product/package generation, packaging descriptor/material/quantity extraction, imperial units, locale/fraction/scientific numeric interpretation or advanced uncertainty extraction. Numeric source values and units must be adjacent literal pairs; separate-unit table columns may need deterministic/manual review. Unsupported/unknown sources are conservatively quarantined. There is no confidence-driven conflict resolution or physical verification.

Synchronous processing occupies a worker; durable queue orchestration, automatic recovery and exactly-once external billing are not claimed. Parser hard memory/CPU limits remain Linux-specific; Windows has bounded inputs/output and wall timeout. SDK request timeouts do not guarantee a global application latency SLO. Source authenticity and semantic attribution need human checking. No formal exhaustive accessibility/browser/device matrix, enterprise penetration test, production ingress test or hardware validation is claimed. Compose runtime and hosted CI are unverified for this phase; the prior Docker networking blocker remains a release gate.

## G. Git status

All changes remain unstaged/uncommitted on `main`. No stage, commit or push command was performed. Existing Phase 5 work, `.env`, database records/volumes and migrations were preserved; only additive Phase 6 migrations were applied. `git diff --cached --stat` is empty. No secret is included in the source changes.

## H. Phase 7 readiness

The source→candidate→validated review→reported catalog claim→explicit deterministic reassessment boundary is implemented and tested. Agree Phase 7 requirements before adding further scope. Outstanding prerequisites include separately authorized live-provider validation if wanted, selected model/data policy, representative document quality evaluation, customer evidence acceptance, deployment worker/timeouts and shared abuse controls, production scanner/storage/retention/restore, Docker host networking, hosted CI and release security review. No Phase 7 work was implemented.
