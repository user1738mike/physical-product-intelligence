# Completion checkpoint

Branch: `codex/v1-completion`. Starting revision:
`ed66912080c04a4c44747735c67445511091ea72`. Inspect actual Git on resumption.
The inherited checkout was clean; origin fetch/push both point to the existing
`https://github.com/user1738mike/physical-product-intelligence.git`.
No remote publication has occurred for this completion work yet.

Read [completion plan](completion-plan.md) and [acceptance](final-acceptance-report.md)
before continuing. Master prompt is the 2026-10-17 user attachment
`0ae7657a-b80e-4d3c-baeb-2749d6112a62/Pasted text.txt`.

Current increment: supervised webhook delivery, abandoned extraction fencing and
expired operational counter cleanup. Added bounded cycle, signal-aware daemon,
separate Compose worker using protected owner configuration, no automatic AI or
payment initiation, and real PostgreSQL regression tests with mocked transport.

Verification: `artifacts/completion-processors-tests.log` first run
failed because an in-process management command closed a Django TestCase
transaction connection. Tests now use actual TransactionTestCase boundaries;
rerun r2 passed five tests. Final `artifacts/completion-processors-tests-r3.log`
passed six tests, including two real daemon starts and clean SIGTERM stops,
on PostgreSQL in 13.011 seconds. Ruff check/format (25 operations files),
Compose merged configuration validation and `git diff --check` passed.
No assertions weakened. Full integrated checks still pending.

Processor slice committed as `ae84540` (inspect actual HEAD before resuming).
Current second slice implements ID-03: additive `accounts.RecoveryGrant` model,
owner-issued 256-bit secret with one-way verifier, expiry/revocation/password
binding, atomic redemption/password change, CSRF/shared limits, session and
issued-credential revocation, customer forms, guarded browser fixtures/redaction,
and operating guide. No email assumptions or customer messages.

Executed `accounts operations.test_processors`: 28 PostgreSQL tests passed in
19.244s (`artifacts/completion-recovery-tests.log`). Subsequently added a real
runtime-role issuance/immutability/redemption test. Full backend run passed
302 tests, zero skips, in 541.931s (`completion-identity-backend-full.log`);
schema validation and 18/18 mock evaluation passed. Drift reported no changes
but warned that the explicitly nonexistent base test DB was absent; repeat
migration consistency against the newly created actual rehearsal DB.
Frontend 59 tests/style/lint/types and recovery production build passed.
Completed membership/settings screen adds roles, removal, ownership transfer,
suspension/reactivation, rename and audit pagination; new final frontend build
passed at `completion-frontend-identity-build.log` (image `2aac3770bb19`).
Final backend runtime build passed (`e6b616a21a85`), browser rebuild still running
session23823 (`completion-browser-identity-final-build.log`). No image published.

Important operational repair: release.py `--processors` creates a new guarded
operator and includes actual Compose worker supervision; backup/rollout/rollback
quiesce this writer too. Existing manifests remain compatible. Script suite first
failed Windows sandbox tempfile permissions; unsandboxed rerun passed16 tests in
0.413s (`completion-identity-script-tests-unsandboxed.log`). Ruff all196 files and
whitespace checks passed after splitting the long regression SQL string.

New isolated rehearsal `artifacts/completion-identity-rehearsal` prepared with
processors, project `ppi-rehearsal-b1af236888`, DB `ppi_rehearsal_b1af236888`,
loopback HTTPS22443. Start passed; all six services including processors healthy.
Phase2 and product/ingestion/compatibility/recorded-extraction smokes passed,
including200 repeated reads and real ClamAV/private downloads; receipts
`completion-identity-phase2-smoke.log` and `completion-identity-product-smoke.log`.
Runtime dependency/Django/schema/drift/applied-migration checks passed against the
actual new DB (`completion-identity-runtime-checks.log`); live provider check
correctly reports explicit authorization required, zero calls.
Browser image final build passed (`264dc9f63dad`); real browser driver running
session61820, output `artifacts/completion-identity-browser`, driver receipt
`completion-identity-browser-driver.log`, runner `ppi-browser-7af9c3b6e8`.
Existing targets were preserved. Generic local app tags point to this candidate.

Identity acceptance now passed: the first browser run failed at the role
selector's accessible name (wrapping options polluted label text). Fixed proper
htmlFor/id associations; frontend label-fix rebuild passed all59 tests/style/
lint/types/build (`completion-frontend-identity-label-build.log`). Recovery locks
now use NO KEY UPDATE to preserve unrelated tenant FK/audit writes while
serializing resets; all10 targeted recovery tests passed in4.219s
(`completion-recovery-final-tests.log`). Final core image
`sha256:cbefaaf2d87311dc7ae3eefafed627f94f09de25be6988d30b8a4f10cc86f12d`,
frontend `sha256:3c8f493bb72f5dcae99e2496acf3db4348f1756ba64a63ad2a081cb32faa2cb4`.
Actual quiesced backup and rollout passed, including processor stop/resume.
Expanded real Chromium journey passed14 checkpoints in1.6minutes, no skips,
no certificate bypass, zero live AI/payment calls. Receipts/screenshots:
`artifacts/completion-identity-browser-r2`; integration management screenshot
visually reviewed, no secret displayed. Prior failed receipt is preserved.

Exact next task: review/stage/commit the verified identity/runtime slice, then
continue billing inbox/reconciliation supervision and bounded retention/legal
hold controls. Customer settings tests exercise actual member
add/role/remove and independent ownership transfer/suspend/reactivate forms.
Review/fix failures, verify daemon/health and migration grants, then commit this
checked identity/runtime slice. Continue ING-07 retention and OPS-04 billing
inbox/reconciliation processor work. No live payment initiation or AI processing.
The signed manual receiver demonstration may race the automatic dispatcher;
coordinate that isolated demonstration explicitly rather than weakening claims.
Do not stop after that increment.

Supply-chain changed condition: host curl with normal TLS successfully retrieved
official `https://grype.anchore.io/databases/v6/latest.json`; metadata is in ignored
`artifacts/completion-grype-latest.json`, built2026-10-17T06:27:09Z,
schema v6.1.10, checksum
`sha256:4c2b8b0cd02313f74a50c81c457796660c4997565cc2ff211e09cc1880205c10`.
One bounded180-second archive download is active in session44148, public archive
`artifacts/completion-grype-official.tar.zst`; do not import until curl exits0 and
SHA-256 matches. Preserve historical scanner cache. Import into a separate new
cache, validate hash/freshness, retain official provenance and adapt scan tooling
honestly if Grype records a local import path. No vulnerability acceptance yet.

Preserve all existing env files, volumes and reports. Phase10 rehearsal is
`ppi-rehearsal-4a1117fa4d`, HTTPS loopback 21443; protected synthetic configuration
under ignored `artifacts/phase10-rehearsal` must not be printed. The Docker daemon
requires tool escalation after a sandbox pipe denial. Existing Phase10 SDK image
with read-only backend source mount runs isolated PostgreSQL tests. Never mount
or print the root `.env`. No new dependencies, live AI, real payments, remote
deployment or image publication have occurred.

External dependencies remain: merchant/provider/commercial decisions; fresh valid
Grype database; last-observed hosted billing restriction; approved staging target;
authorized live AI quality check if required. These do not block independent code.
