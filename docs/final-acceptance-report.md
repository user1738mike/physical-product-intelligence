# V1 completion acceptance

Baseline ed66912080c04a4c44747735c67445511091ea72; completion branch
codex/v1-completion. Historical evidence and the original dirty manifest are
preserved. Final publication identity and hashes will be recorded separately
under ignored artifacts/completion-publication.json to avoid a self-SHA loop.

| Gate | State | Remaining requirement |
| --- | --- | --- |
| IMPLEMENTATION COMPLETE | BLOCKED | Required concrete payment adapter; grounded merchant/provider/commercial decisions unavailable |
| LOCAL ACCEPTANCE PASSED | BLOCKED | functional acceptance passed; image security gate open; Valid final image findings must satisfy unchanged High/Critical policy |
| HOSTED CI PASSED | BLOCKED until an exact candidate pass is recorded | All nine jobs must pass; exact SHA/run inspection is recorded separately in completion-publication.json; prior billing restriction |
| STAGING VALIDATED | BLOCKED | Passing security/CI, approved host/domain/region/budget and deploy authorization |
| PRODUCTION VERIFIED | BLOCKED | Staging acceptance and authorized production deployment/verification |
| PAID COMMERCIAL READY | BLOCKED | Grounded merchant/provider/currency/prices/tax/refund/renewal policy, concrete sandbox-verified adapter and production gates |

The [requirement matrix](completion-plan.md) reconciles Phase1–10 against actual
code and original scope. Conditional OCR and later physical testing are not
silently represented as implemented promises. Deterministic rules remain the
assessment authority; AI output is grounded review material, never a canonical
write or safety certification. Live quality/connectivity was not authorized.

Completion changes include supervised webhook dispatch/stale extraction fencing,
bounded billing reconciliation, private operator-assisted single-use account
recovery, organization/membership/ownership/lifecycle customer flows, explicit
owner-controlled unused original-file disposal with preservation defaults and
legal hold, durable uncertainty/reconciliation, DB guards and retention-aware
backup/restore. Billing remains disabled by default; simulator results never
claim a real payment provider. See [retention](source-retention.md),
[security review](completion-security-review.md) and
[deployment handoff](completion-deployment.md).

Executed evidence (ignored artifacts; identities recorded in receipts):

| Verification | Result and evidence |
| --- | --- |
| Final full backend | 323 passed219.795s; completion-final323-backend.log |
| Final delayed-removal fencing | 38 affected passed27.191s including11 retention cases; completion-cleanup-fence-tests.log |
| Frontend source/build | 59 passed; formatting/lint/types/production build passed; completion-retention-frontend-build.log |
| Mocked release tools/style | 29 passed0.515s; completion-script-checks-final-r3.log; Ruff211 files passed |
| Patched supported bases | Node24/Postgres17 Trixie, nginx1.30.6, unused runtime npm removed; no dependency lock change |
| Actual session/business smoke | Login/CSRF/cookies/logout/tenant/role; CSV/XLSX/text PDF/TXT, real ClamAV, reviewed imports, deterministic assessments and recorded AI passed |
| Final browser | 15 checkpoints passed; completion-fenced-browser; confirmed removed-state PNG inspected |
| Signed integration current R5 | Passed; completion-fenced-integration-demo/receipt.json; two signature-verified deliveries/one receiver effect, credential revocation401 |
| Legacy recovery | 57 models/5 files restored into a NEW Trixie cluster; hashes/counts/forward migrations, narrow DB role, actual HTTPS login/private file/5 immutable assessments/tenant denials passed; legacy-restore.json and legacy-https.json |
| Post-removal recovery | 59 models/5 retained files restored; confirmed removed sources not resurrected; completion-post-removal-restore.log |
| Paired compatible rollback/forward | Passed; completion-paired-rollback-patched.log and rollback-controls.json; quotas/suspension/expiry/tenant/private/history/scoped keys/revoke/unconfigured outbound denial |
| Dependency failures/restart | DB live200/ready503/recovery200/session/history passed; real EICAR rejected/scanner down fails closed; restart/private hash/snapshots passed |
| Measured read workload | 240 reads,4 concurrent,0errors,3.508s,68.41rps,p50 54.28ms,p95 88.89ms,p99 127.38ms; completion-fenced-load.log |
| Runtime consistency | Actual production-control rehearsal DB checks, drift/migrations/schema validation passed; completion-r5-production-consistency.log |
| Mock AI evaluation | 18/18 matched,0provider calls; no live accuracy/precision/recall claim |
| Vulnerability evidence | Official fresh DB transfer/attestation resolved; valid earlier scans FAILED High/Critical policy; available supported fixes applied, selected eight-image results in completion-release-image-scans-r3; final identity/result bindings in completion-publication.json |

Receipts for current operational tests are under
artifacts/completion-patched-rehearsal. Final functional driver is artifacts/completion-final-checks-driver.log.
The remediated rollback retains2181 identical application files/symlinks; its
paired rollback/forward passed. Final selected scan driver is
artifacts/completion-release-image-scan-r3-driver.log. No failed receipt was overwritten.
One earlier full-suite/browser attempt suffered measured host contention and
strict startup/deadline failures; unchanged sequential repeats passed. Four
historical same-workspace rehearsals were reversibly paused, preserving all
containers/volumes/data; exact resume IDs are recorded in
artifacts/completion-historical-rehearsal-pause.json. Prior b1 target was backed up
and stopped. Development and unrelated services were not changed.

Rollback helper failures were corrected without changing product contracts:
production deliberately disables outbound transport; POST-only destinations
correctly reject GET405. Final helper checks the management endpoint and correct
configured denial, while signed deliveries are tested on guarded rehearsal.

Local load thresholds remain <=30seconds, p95<=1500ms and zero errors on Docker
8CPU/8178565120bytes. This bounded authenticated read workload does not establish
write/extraction saturation or production capacity. Qualify the approved target.

Representative executed commands (generated env files are protected, never
printed; all fixture/cleanup targets are synthetic and isolated):

```sh
docker run --rm --network ppi-rehearsal-e908f9a5f5_default \
  --env-file artifacts/completion-patched-rehearsal/migration.env \
  -e POSTGRES_DB=ppi_completion_final323 \
  -e DJANGO_SETTINGS_MODULE=config.settings.test \
  -e INGESTION_SCANNER= -e TRUSTED_PROXY_CIDRS= \
  -v ppi-rehearsal-e908f9a5f5_rehearsal_tls:/certs:ro \
  --entrypoint python ppi-completion-retention-sdk manage.py test \
  accounts organizations operations products ingestion compatibility commercial billing integrations --noinput
python -m unittest discover -s scripts -p 'test_*.py'
python -m ruff check backend scripts --config backend/pyproject.toml
python -m ruff format --check backend scripts --config backend/pyproject.toml
python scripts/integration_demo.py --directory artifacts/completion-patched-rehearsal --output artifacts/completion-fenced-integration-demo
python scripts/browser_acceptance.py --directory artifacts/completion-patched-rehearsal --output artifacts/completion-fenced-browser --commercial-fixtures --billing-fixtures --integration-fixtures --recovery-fixtures --retention-fixtures
python scripts/release_probes.py --directory artifacts/completion-patched-rehearsal --load --observe-seconds 30
```

Frontend verification ran `npm run format:check`, `npm run lint`,
`npm run typecheck`, `npm test` and `npm run build` using the locked dependencies.
Final runtime consistency used `config.settings.rehearsal` with its actual TLS
database and `INGESTION_STORAGE_ROOT=/var/lib/ppi/private`: `manage.py check`,
`makemigrations --check --dry-run`, `migrate --check`,
`spectacular --validate --fail-on-warn`, `evaluate_extraction` and
`check_ai_provider` without a live flag. `pip check` passed in the same SDK image.

Remaining smallest external actions: obtain supported patched image packages or
trusted vulnerability DB corrections, rerun affected scans/acceptance; resolve
hosted billing execution restriction under existing owner settings if confirmed;
provide grounded merchant/provider/commercial decisions and authorized sandbox;
approve staging host/domain/region/budget/deployment boundary. Live AI validation
needs separately bounded authorization and approved fixtures. No billing settings,
secrets, DNS, infrastructure, live AI/payment, remote deployment or image
publication were changed by this work.
