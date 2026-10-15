# AI-assisted specification extraction

Phase 6 extends existing ingestion with optional, source-grounded candidate extraction. The workflow is: private upload → bounded text → candidates → deterministic validation → explicit human review → transactional application → a separately requested deterministic assessment. AI cannot select tenants, choose evidence IDs, change equipment/rules, activate rules, declare compatibility or rewrite assessments.

## Configuration and privacy

Core dependencies and startup do not require an AI provider. Default configuration is disabled even when an API key exists. The optional adapter uses the official OpenAI Python SDK and Responses structured output contract, checked against the [official structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses). Application validation remains authoritative after schema-constrained generation.

| Setting | Behavior |
| --- | --- |
| AI_EXTRACTION_ENABLED | false by default; explicit true enables the capability if other prerequisites exist |
| AI_EXTRACTION_PROVIDER | openai; unsupported values are unavailable |
| AI_EXTRACTION_MODEL | operator-selected compatible model; blank means unavailable; clients cannot supply it |
| OPENAI_API_KEY | reused directly from secure backend environment; never browser configuration |
| INSTALL_AI_SDK | Compose build option, false by default; true installs the optional locked SDK extra |

Install the optional runtime with `python -m pip install -r backend/requirements-ai.lock`. `requirements-ai.in` records the direct input; the optional lock includes the unchanged core lock and exact SDK/transitive versions. Compose passes settings/key only to backend and builds the extra only when requested. Use `docker compose config --quiet`, since unredacted Compose configuration can expose resolved secrets. Never enable provider calls as part of a routine test or CI job. This implementation was verified without live calls; model/account compatibility and provider-side access are not proven.

Existing `.env` files are preserved. `.env.example` has configuration defaults only; no key was copied or created. Production should inject the secret from its established secret manager. Never use NEXT_PUBLIC variables, place credentials in candidate metadata or include keys in prompts/logs. Missing key, model, SDK, disabled configuration or unsupported provider gives an explicit unavailable state; the rest of the application continues working.

Queueing does not send data. Only the explicit processing action sends the bounded extracted text/segments from the selected source to `https://api.openai.com/v1`. It sends no catalog records, organization/user IDs, unrelated evidence or tools. The SDK receives the configured credential for authentication, not in the model input. Ambient OPENAI_BASE_URL is ignored. Response storage is requested off (`store=false`); this is not a claim about all provider retention or jurisdiction policies. Operators must approve the source data's transmission, provider policy and region/account configuration before enabling. Do not upload private secrets in source documents; an uploaded document's own sensitive content may be transmitted as source text.

The adapter is replaceable through the `ExtractionProvider.extract(segments) -> (JSON text, bounded usage)` protocol and server-owned factory. Adding a provider requires reviewed backend code; arbitrary browser-selected endpoints/models or dynamic plugins are prohibited. SDK/HTTP diagnostic loggers are suppressed during extraction, and provider exceptions are reduced to fixed categories. Audit records retain IDs/actions and safe processing metadata, not complete prompts or raw provider exception bodies.

## Sources and extraction schema

Supported sources are the original Phase 4 private PDF/TXT/CSV/XLSX uploads. No second file/evidence store is created; extraction jobs reference the original upload's bytes/checksum. Source downloads remain authenticated. Integrity/checksum and production malware-scanning checks apply before extraction, review and application.

PDF uses bounded text extraction with actual page and extracted-text offsets. TXT uses decoded character offsets, never fabricated page numbers. Tables preserve selected sheet/row location and header/value text. Formula/macro/archive and parser safeguards remain in force. Table row errors fail the AI parse instead of silently omitting rows. Scans/OCR, images, arbitrary binaries, external document fetching and remote URLs are unsupported. Existing table options are inherited from the original import; use deterministic validation first to choose a nondefault worksheet/header/delimiter.

Only these attributes are supported: length, width, height, mass, name, brand, manufacturer and description. Numeric attributes target the explicitly chosen product or existing active packaging profile. Text identity fields target the product. New-product creation, packaging-descriptor inference, shape/material/quantity extraction and automatic target identification are deferred; create the target through the catalog first.

Schema `grounded-spec-v1`:

```json
{"candidates":[{"attribute":"mass","value":"1200","unit":"g","original":"1200 g","segment":1,"quote":"Weight: 1200 g"}]}
```

All item keys are required. `value` and `segment` can be null for unresolved value/location. No confidence number is invented. Extra fields, arbitrary evidence/tenant IDs and wrong field types are quarantined; malformed/duplicate-key JSON or an invalid top-level envelope fails the job. More than 30 candidates or an oversized output fails rather than truncates.

The server assigns source identity and maps segment IDs to the exact supplied text. Quote must occur verbatim in that segment; original text must occur within the quote. A proposed numeric value/unit pair must literally occur together in the original, with token boundaries that prevent borrowing digits from a negative number, fraction or adjacent number. Separate table unit cells, locale numbers, inferred units and complex tolerances may therefore require deterministic/manual review. A mapped source excerpt establishes textual support, not semantic correctness or manufacturer authenticity.

Only application code normalizes mm/cm/m to mm and g/kg to kg using existing Decimal `metric-v1` conversion. Original text/value/unit and normalized operands remain separate. Zero, negative/nonfinite values, overprecision, dimension/mass mismatches, unsupported units, formulas and unknown attributes cannot become valid observations. Unsupported numeric grammar is not guessed.

Valid source locations are retained even for an explicit unknown value. Values whose location cannot be validated are preserved as quarantined candidates with unavailable source location. Unknown/ungrounded output cannot be approved into the catalog; inspect the original source and use the existing manual workflow or a corrected extraction. Grounded candidates with deterministic value/unit issues may be corrected explicitly with reviewer rationale. Corrections retain the original and decision history and are human assertions, not physical measurements.

## Jobs, processing and resource bounds

ImportJob gains `mode`, `source_job`, tenant/request UUID uniqueness and extraction metadata. Candidate gains extraction metadata. Existing ImportRow, ReviewRecord, evidence, claims, canonical selection and assessment records are reused. Extraction jobs reference stored bytes rather than copying them; the upload byte quota counts original uploads once. An extraction cannot use another extraction as its source.

| State | Meaning |
| --- | --- |
| uploaded with extraction.stage=queued | Registered targets/source; no provider call yet |
| processing | Persisted bounded processing lease; no catalog writes |
| awaiting_review | Candidates and original provenance persisted, including invalid/unknown ones |
| completed / completed_with_errors | Human-reviewed application completed; rejected/skipped items are reported; zero candidates finishes with errors |
| failed | Processing/persistence failed safely; fixed error category and explicit retry eligibility |
| cancelled | Catalog unchanged; outstanding responses are discarded |

Starting the same request UUID with identical source/targets returns the same job; different operands return 409. Active leases prevent duplicate final persistence. At most one fresh extraction processes per tenant, with a PostgreSQL-wide cap of two across tenants/instances (`AI_EXTRACTION_MAX_CONCURRENT`, bounded 1–8). Each job has at most three attempts, no automatic SDK retry, an 8-second provider request timeout, maximum 2,500 generated tokens and 24,000 output bytes accepted by the application. Source limits are 24,000 characters and 80 segments, with existing 2 MiB upload/10 PDF page/parser CPU/memory/20-second wall limits. Long sources must be split explicitly; text is never silently truncated to produce a favorable result. Ordinary mutation requests retain the 64 KiB cap. Extraction writes use shared PostgreSQL fixed-window limits of 20/hour per user and authorized organization, plus the existing 20-unfinished-import bound. See the [operations guide](deployment-and-operations.md) for proxy trust, fail-closed 503/429 behavior, synchronous capacity and ingress controls.

Timeout, rate-limit and transient availability failures permit explicit retry until the attempt limit. Permanent authorization, output/validation and processing failures do not retry; correct the configuration/source and create a new request when appropriate. An interrupted processing lease can be recovered after 90 seconds with the current version, up to the same attempt bound. Recovery cannot guarantee exactly-once provider billing if a process dies after sending a request. The lease does prevent duplicate candidate persistence. There is no durable queue or automatic scheduler.

Processing does not hold database locks across the provider request. Finish reacquires organization/job locks and rechecks current role/source/target scope and the lease. Cancellation/late responses cannot win after state changes. Review and application remain transactional under the organization lock. Failed candidate persistence rolls back all partial rows and records a failed state. If the initiating user's access is revoked while processing, persistence is denied; an authorized owner/admin can recover or cancel the expired lease. App workers must allow enough timeout for parser plus provider work; proxies may time out earlier, in which case inspect job state before retrying.

Counters show candidate/invalid counts, pending/approved/rejected decisions and application results. Metadata includes provider/model/schema/time, duration, attempts, safe failure category, text checksum and bounded token counts when available. No exact pricing or savings are claimed. Source excerpts exist in authorized candidate/provenance records, not operational logs.

## Review, conflict and deterministic assessment boundaries

All current active members read jobs/candidates/source/history. Owner/admin is required to queue/process/retry/cancel AI work and to review/apply. There is no staff bypass. Browser identifiers are selectors; current membership and same-tenant product/package/source relationships are checked server-side. PostgreSQL deferred triggers additionally validate extraction source identity and row/product/package/evidence scope. These are not RLS or protection against trusted database operators.

Each candidate is approved/rejected individually with a reason, optionally corrected, using existing optimistic versions. Identical repeated decisions succeed without duplicate history. Application requires all candidates decided, revalidates approved values and source bytes, rejects changed catalog/claim targets and uses existing domain services in one transaction. Refresh comparisons invalidates approvals; review again. Cancellation retains source/history.

Equivalent supported units compare by deterministic canonical values. Exact/equivalent duplicates and contradictory candidates remain separate assertions; conflicting candidates are annotated with peers. Existing claims/canonical values are compared and preserved. Confidence never resolves disagreement. Approval alone records acceptance for application; numeric canonical selection additionally requires the explicit selection checkbox. Applying approved values creates **reported** claims and immutable source-linked revisions, never physically measured claims. Prior canonical selections and conflicting claims remain in history; unsupported simultaneous competing selections are rejected. Descriptors require explicit approval as well.

Existing assessments remain unchanged. New assessments must be requested with a new request UUID and selected activated rule version. Phase 5 still treats missing/conflicting required evidence conservatively; editorial canonical selection does not erase disagreement. Assessment claim/evidence snapshots now retain AI extraction provenance, including source excerpt/model/schema, so later metadata does not reinterpret history. No extraction code calls rule mutation, activation or assessment services. Tests separately demonstrate extraction unchanged→review/apply→new deterministic result, with old input snapshots and rule definitions byte-for-byte unchanged.

## API

Paths relative to `/api/v1/organizations/{organization_id}/imports/`:

| Endpoint | Contract |
| --- | --- |
| GET ai-capabilities/ | Availability/reason, schema/limits, privacy notice; never a provider request |
| POST {source}/extractions/ | `{request_id, product_id, packaging_id?}`; creates/reuses queued job |
| POST {job}/ai-process/ | `{expected_version}`; explicit process, eligible retry or expired-lease recovery |
| GET {job}/ | Existing job status, counters/errors and extraction metadata |
| GET {job}/candidates/ | Existing paginated decision/quality filters and source metadata |
| GET {job}/candidates/{candidate}/ | Candidate detail |
| POST {job}/candidates/{candidate}/review/ | Existing versioned approve/reject/correct/select/rationale contract |
| POST {job}/refresh/ | Refresh current targets/comparisons and invalidate approvals |
| POST {job}/apply/ | Apply all reviewed changes atomically and idempotently |
| POST {job}/cancel/ | Cancel queued/review/failed/in-flight extraction; discard late output |
| GET {job}/history/; file/; errors/; rows/ | Existing authorized history, private source and diagnostic records |

All mutations use the existing session plus fresh CSRF token. Foreign tenants/nested objects use 404, role/session/CSRF denial follows existing 403 convention, stale/reused-conflicting requests 409, validation 400, and unavailable capability 503 without a new job. Deterministic validate/mapping/process endpoints reject AI jobs; the explicit AI processing endpoint rejects ordinary import jobs. No client can supply provider URL, model, key, verification state, arbitrary field path or evidence ownership.

Example queue request (`POST {source}/extractions/`):

```json
{"request_id":"8ce3b1c3-581c-4eb6-9c28-d3bb30c34ec5","product_id":"PRODUCT_UUID","packaging_id":"PACKAGE_UUID"}
```

Replace target labels with real returned UUIDs. Queueing returns an ordinary job object with `mode=ai`, `status=uploaded`, `extraction.stage=queued`. Explicit process creates candidates with retained `raw_value`, proposed/normalized values, existing claims/quality, source location/excerpt, extraction provenance, errors and decision state. It never returns a fabricated success when the provider failed.

## UI and verification

Open an original import to check availability, search/select the actual product/package and queue extraction. The queued job requires a separate clearly labeled source-transmission action. When disabled, the deterministic/manual path remains usable. AI jobs expose status/retry/cancel, candidate quality/excerpts, existing values, correction/approval/rejection and the existing atomic application/history controls. Unknown/ungrounded candidates default to rejection and cannot select approval in the form; server validation remains authoritative.

Run the full backend suite with `python manage.py test accounts organizations operations products ingestion compatibility --settings=config.settings.test` against PostgreSQL. `ingestion.test_ai` supplies mocked provider tests and SDK MockTransport checks; the three actual SDK checks skip explicitly when the optional extra is absent. CI's native backend job installs the optional lock and runs them without credentials, with AI disabled. Compose's default core image remains usable without the SDK. Frontend: `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run format:check`, `npm.cmd run build`.

The existing disposable Phase 3 proxy smoke includes Phase 4/5 and disabled-provider Phase 6 coverage. It refuses the AI smoke if capability is enabled and never invokes a model. Browser fixtures used for this phase are visibly labeled **MOCKED-OFFLINE-NO-API** and do not demonstrate live extraction quality. See the [completion report](phase6-completion-report.md) for actual results and unverified provider/Docker/CI gates.
