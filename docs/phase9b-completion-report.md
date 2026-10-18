# Phase 9B completion report

Local candidate, 17 October 2026. No real payment provider is configured. This report distinguishes the executable simulator from provider verification and production acceptance.

## A. Prerequisite audit and repairs

Phase 9A is implemented and independently checkpointed in `artifacts/phase9a-manifest.json` and `phase9a-reviewed-source.zip`. Its report records 228 PostgreSQL tests, 42 frontend tests, 18 mocked extraction cases, HTTPS smoke and nine browser checkpoints. Its immutable plans, organization locks, reservations, append-only usage, assignment history and runtime-role protections are reused. Billing never resets usage or silently replaces manual pilot access.

Narrow repairs allow authorized billing/commercial history screens to load for inactive organizations, while their protected APIs remain authoritative. A text-download OpenAPI annotation was corrected. Initial simulator tests exposed a Django settings-module detection error; the corrected guard still requires explicit test settings plus a disposable database identity. Initial frontend compilation rejected BigInt literals under the repository target; BigInt constructors preserve exact arithmetic.

## B. Implementation and invariants

`backend/billing` contains models, two migrations, services, a strictly isolated adapter, session APIs, an operator command, synthetic acceptance fixtures and PostgreSQL tests. Organization enrollment creates an unconfigured account. Immutable versioned prices and finalized statement snapshots use bounded integer minor units and approved currency exponents. Draft revisions require their expected version. Linked corrections preserve settlement balances; finalized history cannot be rewritten.

Durable account-wide request identities bind principal, statement, price, amount, currency, period, environment and expiry before submission. Unknown outcomes retain the original identity and are reconciled without resubmission. Incoming receipts are persisted before acknowledgement, with semantic-conflict detection, bounded claims/retries and stale-worker fencing. Money, allocations and explicit verified-payment access grants commit atomically. Refund observations link their original receipts; disputes remain review observations. No refund is initiated. See [API contracts](billing-api.md) and [operations](billing-operations.md).

Owner/admin session APIs expose scoped history, status and private statement downloads. Members receive 403; foreign/revoked access receives 404. Ordinary staff have no tenant bypass. Customer responses exclude restricted provider identities and operator reasons. The typed Billing history screen supports empty, pending, partial, settled, unknown and action-required states, tenant switching and refresh, without a nonfunctional payment button.

## C. Actual provider boundary

There is **no real adapter, merchant account, checkout URL or collection capability**. The offline simulator runs only with explicit test/rehearsal settings and a guarded database name. Its public synthetic HMAC proof is not a provider signature mechanism. Production rejects simulator/provider enablement. Test events cannot settle live records. No API/payment signing secrets were created, read, changed or reused.

USD/EUR/KES, JPY and KWD exponent metadata was checked against the official SIX ISO 4217 list. XTS has no ISO minor unit; exponent zero is an explicit simulator convention only. No customer prices, taxes, renewal, proration, grace period or currency selection are invented. Public collection availability remains false.

## D. Verification

| Check | Classification and evidence |
| --- | --- |
| Final backend | **Executed/passed: 261 tests, zero skips, 156.082s**, PostgreSQL 17, `artifacts/phase9b-backend-final-candidate.log`. Command: `docker run --rm --network ppi-rehearsal-adb8f69298_default --env-file artifacts/phase9a-rehearsal/migration.env -e POSTGRES_DB=ppi_phase9b_validation -e DJANGO_SETTINGS_MODULE=config.settings.test -e INGESTION_SCANNER= -e TRUSTED_PROXY_CIDRS= -v ppi-rehearsal-adb8f69298_rehearsal_tls:/certs:ro --entrypoint python ppi-phase9b-backend-sdk manage.py test accounts organizations operations products ingestion compatibility commercial billing --noinput`. Includes 32 billing tests plus the upgrade regression; real concurrent request/completion/claim tests, rollback, runtime SQL guards, scope/mode isolation, signatures, durable receipt/storage failure, partial/refund/dispute/late events and uncertain-submission reconciliation. |
| Frontend | **Executed/passed:** 54 tests/10 files, format, lint, types and Next.js webpack production build; `artifacts/phase9b-build-frontend-final.log`. Twelve billing tests cover exact money, states, switching and stale responses. |
| Dependencies/migrations/schema | **Executed/passed:** pip check, Django check, migration drift/applied checks and spectacular validation with fail-on-warning; `artifacts/phase9b-backend-checks-final.log`. |
| Extraction | **Executed/passed:** 18/18 deterministic fixture expectations, zero provider calls. Live check correctly reports not executed because authorization is absent. |
| Scripts/config/style | **Executed/passed:** 15 script tests; corrected production configuration including two unsafe simulator negative checks; Ruff check/format with repository configuration, 162 Python files. The initial production schema warning is retained in the earlier script log; the corrected check passed separately. |
| HTTPS smoke | **Executed/passed:** phase2 and recorded phase3 workflows on port 20443, including 200 repeated proxy reads, CSRF/cookies, logout, tenant/role denial, ingestion/scanner, review and compatibility; `phase9b-smoke.log` and `phase9b-smoke-context.log`. |
| Browser | **Executed/passed:** real sandboxed Chromium, ten checkpoints, including delayed durable confirmation, actual settlement/download, partial/unknown/action-required states, owner/admin/member/revoked isolation and tenant switching. The bounded fixture processor receipt confirms applied events. Exact runner/image identities are recorded in `artifacts/phase9b-manifest.json` and `phase9b-browser-final`; screenshot visually reviewed. The initial driver invocation failed before browser execution because the synthetic context had not been generated; the actual authenticated smoke workflow generated that context before retry. |
| Builds | **Executed/passed:** new offline local runtime/SDK/frontend/browser builds from preserved immutable verified local bases, with network disabled and no dependency changes. Standard registry-based recipes remain **blocked** by previously observed metadata TLS/authorization failures; offline verification does not claim a hosted build. |
| Image acceptance | **Blocked:** seven current images inventoried; invalid/missing/old official Grype DB rejected with automatic update disabled. `artifacts/phase9b-scans/summary.json`. No zero-finding claim. |
| Hosted CI | **Blocked/unexecuted:** candidate is uncommitted; published Phase 8B CI was prevented from starting by account billing. No settings changed. |
| Staging/real provider | **Blocked/not executed:** no approved target/domain/region/budget or selected merchant/provider and authorized sandbox integration. |

## E. Migration, grants and recovery

Fresh isolated rehearsal `ppi-rehearsal-0f8447b65d`, database `ppi_rehearsal_0f8447b65d`, HTTPS port 20443 applied migrations and narrowed actual runtime grants. Owner-only prices, statements, financial history and processors are unavailable to the HTTP role. It can enroll only blank accounts and insert bounded operations/receipts/audits; it cannot rewrite their histories. Triggers enforce immutable identities, arithmetic, tenant/mode links, allocation/refund limits and verified access links.

The executed upgrade regression removes/reapplies billing only in a disposable `test_` PostgreSQL database. It proves preexisting products, plan assignment and metering start survive, accounts backfill unconfigured, and no money, statements, prices or historical usage are fabricated. No existing development, Phase 8B or Phase 9A database was migrated for this check. Actual customer/staging upgrade/restore remains documented/not executed.

Bounded operator `process`/`reconcile` require actor, reason, organization and limit; dry-run is default. Claims commit before adapter I/O and fenced results cannot overwrite newer work. Missing simulator deliveries can be recovered from authoritative local state; ambiguous charges are never repeated. Retention, backup encryption, owner-connection isolation and target-specific restore/grant verification remain required.

## F. Remaining decisions and release gates

Select provider/merchant ownership, approved prices/currencies, taxes/invoice requirements, renewal/cancellation/grace and refund/dispute policies, then authorize real-adapter sandbox verification. Simulator success is insufficient for real collection. Obtain an acceptable fresh Grype DB and scan these images. Resolve GitHub account billing before authorized publication/exact-SHA hosted CI. Approve a staging host, domain, region and budget before deployment validation. No production release is approved.

## G. Git and external actions

During verification, the checkout advanced externally to `3e26f68f6dcffb8a4c40abadf9a8abd600803427` on `codex/phase9b-billing-workflows`, containing the implementation. The agent did not invoke stage/commit/push. This report remains an unstaged addition. Phase 9A branch/checkpoint and historical dirty-build manifest are preserved. Source/image/evidence identities are recorded separately, without substituting new evidence into historical manifests. Root `.env` remains untouched (475 bytes, original October 14 timestamp). The agent performed no push, merge, image publication, remote deployment, purchase, billing/DNS/secret setting change, real payment/refund or live AI call. External currency metadata was read; testing used local synthetic data and existing images.

## H. Readiness

Local billing orchestration is implemented and tested. Real-adapter sandbox verification is **not executed**. Live collection is **unavailable**. Hosted, staging and production acceptance remain **blocked**. Phase 10 may reuse these local foundations while keeping payment and release gates open; it must not relabel this simulator as a payment integration.
