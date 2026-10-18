# Completion checkpoint

Branch: codex/v1-completion. Baseline ed66912080c04a4c44747735c67445511091ea72.
Committed increments: ae84540 maintenance, 730e9eb recovery/customer organization
journeys, 8b01733 billing supervision, c887a91 retention/recovery and c1f9bea
release recovery, supported image remediation and trusted scan/CI gates.
109f427 adds ownership-checked cleanup and a300second bound for database validation.
The r2 scan attempt timed out in prevalidation and is blocked evidence, not a clean
result; its unlabelled helper subsequently exited. Final r3 retains hash/freshness
and severity checks with bounded owned-process cleanup.
Final source/publication/hosted outcomes are recorded outside Git in
artifacts/completion-publication.json, avoiding a self-SHA commit loop.

Current generated target: artifacts/completion-patched-rehearsal,
project ppi-rehearsal-e908f9a5f5, https://127.0.0.1:23443. Seven services healthy.
Core backend d268f09eff43, optional SDK31c489cfcd2d, frontend2dcc1b64dbef,
PostgreSQL2d2b8998d310, ingress8078564a9faf, ClamAV638d90201ee7.
Full identities and protected configuration are in its ignored release.json.
Never print journey.json or env files. Root .env was never read or modified.

Preserved increment evidence (final integrated results follow):
- Full322 backend repeat passed504.219s before the final delayed-removal fence.
- Final fence:38 affected backend tests passed27.191s, including11 retention cases.
- Frontend59 tests, format/lint/types and production build passed; final standalone
  output unchanged when moved to supported patched Node24 Trixie runtime.
- Actual patched-base browser15 checkpoints passed2min; positive removed-state
  assertion and screenshot verified. Final R5 repetition passed below.
- Current auth/CSRF/cookie/logout and full catalog/import/review/compatibility smoke
  passed through real TLS proxy and ClamAV; AI uses recorded fixtures only.
- Legacy57-model/5-file restore into NEW Trixie cluster passed, including actual
  HTTPS sessions, private hash,5 snapshots and tenant denials. Existing DB volumes
  were never attached to a different PostgreSQL OS image.
- Current post-removal59-model/5-file backup/restore passed; confirmed removals
  were not resurrected. DB outage, EICAR/scanner outage, restart/private snapshots
  passed. Receipts remain under artifacts/completion-patched-rehearsal.
- Paired rollback0a0d1caa3eae/3c8f493bb72f passed commercial/tenant/private/history,
  scoped credentials, revoke, unconfigured outbound denial; forward rollout passed.
  Driver completion-paired-rollback-r4.log. Earlier helper failures are preserved:
  production intentionally disables outbound; POST-only destinations GET gave405.
- Release-tool29 mocked tests passed0.515s; Ruff all211 files passes.

Final integrated checks executed/passed:323 backend tests in219.795s,
59 frontend tests/build,29 mocked tool checks,15 browser checkpoints, actual
production-control DB drift/migrations/schema/dependency checks and18/18 offline
evaluation. Current signed receiver, read workload and30s readiness passed:
240requests/4concurrency/0errors,3.508s,68.41rps,p95 88.89ms. Runtime source binding
matches188 files in both immutable backend variants. Current browser PNG inspected.
Receipts: completion-final323-backend.log, completion-fenced-browser,
completion-fenced-integration-demo, completion-r5-production-consistency.log,
completion-fenced-load.log and completion-image-source-binding.json.

Patched compatible rollback frontend eeca9c22bdf3 replaces3c8f493bb72f:
all2181 application files/symlinks match the predecessor; patched supported Node
runtime removes unused vulnerable npm. Paired rollback/forward repeated/passed:
completion-paired-rollback-patched.log; binding receipt and offline recipe retained.
Final selected eight-image scan set is completion-release-image-scans-r3, including
this patched rollback artifact. The separate final publication record binds those
results to source, exact immutable identities, archive/config/layer checks and
trusted DB provenance. Earlier failures are preserved, never rewritten as passes.

Security database transfer is RESOLVED. Official schema6.1.10 built
2026-10-17T06:27:09Z, pinned Grype0.120.1, archive checksum and fresh-cache DB-content
attestation bind artifacts/completion-grype-provenance.json to
ppi_grype_93f4b1a8d0. Earlier valid scans found genuine High/Critical vulnerabilities.
Applied available nginx1.30.6, Node/Postgres Trixie and unused runtime npm fixes.
Current/SDK/infra/explicit rollback pair scan acceptance is required. Never suppress
unfixed findings, relax severity/freshness, or claim the earlier transfer blocker.

Data preservation: four historical same-workspace rehearsals were reversibly
paused after measured contention; exact resume IDs in
artifacts/completion-historical-rehearsal-pause.json. Previous b1 task target also
backed up and stopped. All containers/volumes/DBs/envs preserved. Development and
unrelated orderdesk untouched. No reset, prune, existing customer file deletion,
live AI, real payment, image publication or remote deployment occurred.
Historical artifacts/phase8-final/release.json SHA256 remains
 aa016293819fd8e46b0937203416f70c0e26a19c73cab4ce9c256d696015d87f.

Publication procedure: final documentation commit, clean-tree source/build/lock/
image/evidence manifest outside Git, ordinary push to verified origin and inspect
exact SHA plus all9 hosted jobs. The generated publication record contains actual
outcomes; do not edit tracked files merely to embed their own SHA. Re-run affected
checks for any future source, dependency or build input change.

External gates: unresolved actual merchant/provider/currency/prices/policies and
sandbox authorization prevent a concrete real payment adapter; no staging target,
domain/region/budget/deploy authorization; hosted billing restriction must be
rechecked after push; residual image vulnerabilities require supported fixes or
trusted database corrections. Live AI quality/connectivity remains unexecuted
without its specific authorization. Report six readiness gates separately.

## Dashboard continuation — 2026-10-18

Active branch `codex/unified-dashboard`, starting from `31f5a19`.
See [dashboard walkthrough](dashboard-walkthrough.md) and requirement rows
DASH-01–06 in the completion plan. The current code adds a persistent shared
organization layout, canonical overview, scoped aggregates and independent
optional summaries while preserving existing business services and permissions.

Verified: frontend 73 tests/format/lint/types/production build; PostgreSQL 331
tests plus final 8-test dashboard repeat; system/migration/schema checks; 29 script
tests; backend style. Test databases were unique and confirmed removed afterward.
Receipts: `artifacts/dashboard-backend-verification.json`, related logs and
`artifacts/dashboard-test-db-teardown.json`.

Fresh rehearsal `ppi-rehearsal-5f1408662b` at `https://127.0.0.1:24443`, state
`artifacts/dashboard-rehearsal-r1`, uses new isolated DB/private storage and the
candidate backend/frontend images. All seven services healthy. Real HTTPS
session and full catalog/import/review/assessment smoke passed. Previous app,
rehearsals, databases, volumes, root `.env` and evidence are unchanged.

Final sandboxed Chromium verification PASSED in `artifacts/dashboard-browser-r4`:
2/2 tests, 28 checkpoints, 157.232s, zero skipped/flaky/unexpected outcomes. Dashboard
console/runtime/hydration and unexpected 5xx counts are zero; 3 injected 503s and 11
expected authorization denials are separately labelled. All three roles, two
organizations, navigation/deep links, stale responses, optional errors/retry,
credential clearing, desktop/tablet/phone focus/contrast and account/logout paths
passed. Desktop/mobile PNGs were inspected. The full existing business journey
also passed after the final primary-link text contrast correction.

Final selected frontend is `1d37cff3ff78`; backend `5d8336bed8b3`. The browser execution
receipt contains full identities. 187 backend source/configuration files match its
immutable core image. Earlier failed r1–r3 receipts remain distinguishable: launcher
line endings, test-client CA trust, test navigation/alert synchronization and the
observed primary-link contrast defect were corrected. Cookie/header redaction has
JSON-preservation regressions and sanitized earlier diagnostic files.

No live provider/payment, image publication or remote deployment occurs. Resume
only affected verification with a NEW browser output directory after inspecting
retained evidence, using the command in the walkthrough. Final commit/push/hosted
outcomes and source/build/evidence bindings are written outside Git to
`artifacts/dashboard-publication.json` after the report commit. Existing global
implementation/security/provider/CI/deployment/commercial gates remain unchanged;
local dashboard success does not assert full v1 or production readiness.
