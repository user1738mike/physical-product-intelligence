# Phase 8B — Release gate closure

Date: 2026-10-16 (Africa/Nairobi). **Real local browser acceptance passed. Production release remains blocked** by unavailable image vulnerability evidence, a GitHub account billing lock, and a missing authorized staging target. No live AI request, secret change, staging/commit/push, image publication, DNS change, purchase or remote deployment was performed.

## A. Starting state and changes

The checkout began clean on `main`, HEAD/local `origin/main` **2cdb78e3ebd270e46d782e6291ef5214b0961bc6**. The user committed Phase 8 after its report; the report's earlier unstaged-work statement remains historical. There were no initial uncommitted user changes to include or discard.

Read the applicable frontend instructions, installed Next.js Playwright guide, Phase 8 report/checklist/plan, retained release manifest, workflows and release/scanner/provider/browser-related code. The retained manifest is an honest dirty build based on3375e31…, not an image originally built from a committed2cdb78e checkout. Its nine selected evidence hashes verified before this follow-up. Its source/journal and original synthetic recovery data were preserved. The application lockfiles remain unchanged: backend core SHA256 `d510d71cdfd31364ca144fd1ddc4df5419dd8312d29e547a0ea71ecae943b799`, optional SDK `e5f6da7a75e4b4576ff31d85578a8c49f7a3af748a2ed7898fc303a81928bf58`, frontend `4bf124410d8260a1c011b491cc355e467c2f0d1f09959da29a4592fa77ae51cb`.

New work: a separate locked Playwright suite/isolated CA-and-sandbox runner; exact-image scan inventory and fail-closed database/threshold regressions; hosted scan/browser evidence retention and infrastructure coverage; a single Linux-host overlay, nginx template and target/configuration handoff. Existing application source, authorization, scanner deadline, deterministic engine and production dependency locks are unchanged. An offline comparison verified112 backend application/fixture/lock files in the tested SDK image match the checkout byte-for-byte.

The previous202/37/11/18 results were initially reported historical evidence. Newly executed checks now include202 backend tests,37 frontend tests,15 script tests,18 synthetic evaluation cases and real browser acceptance. Prior load/recovery/rollback/restart measurements were not repeated: no relevant application/storage/schema change justified doing so. The old240-read/p95≈232ms result remains specific to that earlier workload/environment; no supported-scale inference is made.

## B. Four-gate decision

| Gate | Status | Candidate/artifact and evidence | Remaining action |
| --- | --- | --- | --- |
| Vulnerability acceptance | **Blocked**; frontend npm advisory check passed | Seven exact local image IDs and lock hashes in `artifacts/phase8b-scans/summary.json`; Grype0.120.1 cannot obtain a valid official DB. Final frontend npm audit exit0/zero reported vulnerabilities in `artifacts/phase8b-npm-docker-audit.json`. | Restore an approved working path to the official DB or execute the prepared scans on an authorized working hosted runner; triage all blocking findings. |
| Real local browser acceptance | **Local checks complete — passed** | Chromium **156.0.8078.4**, Playwright **1.64.1**, `https://edge:8443`, actual retained production-like application images. Final1-test journey passed in **54.3s** with8 recorded checkpoints; `artifacts/phase8b-browser-final/{acceptance,execution,browser}.json`, redacted log and screenshot. | Actual staging endpoint/public TLS and broader device/accessibility acceptance remain deployment work; do not relabel this local result as staging. |
| Exact-candidate hosted CI | **Blocked** | [Run38893453197](https://github.com/user1738mike/physical-product-intelligence/actions/runs/38893453197), SHA2cdb78e…, completed/failure, updated2026-10-16T11:23:30Z. All5 baseline jobs were prevented from starting by an account billing lock. New Phase8B files are uncommitted/unpublished. | Account owner resolves GitHub billing lock; separately authorize reviewed commit/push and inspect all required jobs for the resulting SHA. |
| Concrete deployment target | **Blocked** | No authorized host/account, region, domain or budget found. `compose.host.yaml` and rendered nginx passed syntax checks with synthetic inputs only; no target was allocated or deployed. | Supply/approve the specific existing host/account, region/domain/exposure/budget and deployment authorization, then provision protected external configuration. |

Final application identities actually exercised: backend **sha256:4bf33fdf2f6cbeb18217e98c2e5cac0099876695ec9a155acd180ee0d510b921**, frontend **sha256:64c5b87036920e923047e83470978d00c5a33c6b5ff6efbb974d27c3c753395c**. The final browser runner is **sha256:ac89cf6501dd6e32fcc9cf9d35e3be0f9fb50806612e259d663348bbe65b3553**. The SDK test image is recorded in Phase8's manifest/report and remains unchanged. Phase8B's final reviewed-source/evidence chain is recorded separately in `artifacts/phase8b-manifest.json`; no old evidence is relabeled as a new committed release.

## C. Vulnerability diagnosis and coverage

Actual tool: official `anchore/grype:v0.120.1`, immutable local identity `sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe`. Inspected real Phase8 logs: backend/frontend/update attempts failed with **unexpected EOF**, not a successful zero-finding result. The dedicated Docker cache reports missing/invalid DB and an invalid build timestamp. Partial host caches were not treated as verified databases. Disk had approximately131GB available; there was no observed ENOSPC condition. Existing resources were not pruned or removed.

The Grype catalog itself worked and selected schema **v6.1.10**, built **2026-10-16T06:29:51Z**. It supplied today's official archive and SHA256 **9985d2b30dc728eea2941d23e7d7a2e04daebd65c50a959c6136a858927516b9**. This changed artifact justified exactly one explicit import attempt, with a90-second configured download limit and checksum query. It failed with **unexpected EOF at51s**, exit1. No unchanged update/download loop followed. Catalog/import receipts: `artifacts/phase8b-db-list.json` (plain-text catalog output despite its suffix), `phase8b-db-import.log`, `phase8b-scans/database-status.log`.

TLS-verified Python catalog probes on host/container returned HTTP403; the native npm advisory POST failed with socket hang-up. DNS/TLS negotiation can reach these services; no401/429 or certificate-validation error established an authentication/throttling/TLS cause. Working catalog and registry transfers rule out a universal offline state. **Network/transfer failure is the established category; proxy, egress filtering, CDN/server behavior and the exact source of premature termination are not proven.** No network restriction, TLS verification or authentication was bypassed.

The browser builder subsequently reached npm successfully. That changed execution-path evidence justified one bounded application audit in the existing Linux frontend image (`fetch_retries=0`, `fetch_timeout=30000`): **exit0, zero reported vulnerabilities,209 dependency entries**, covering the unchanged frontend lock above. This resolves the frontend npm advisory subcheck; it does not prove why the earlier request failed or clear OS/runtime/backend vulnerabilities. Browser tooling's separate4-package audit also passed during install; it is not application scan coverage.

`scripts/release_scan.py` inventories backend, standalone frontend, PostgreSQL, nginx, ClamAV, optional SDK and prior-code rollback image. All7 image verdicts remain **blocked** before export/scan because the DB precheck fails. Backend core/SDK dependency vulnerability coverage is therefore blocked too; `pip check` below checks consistency, not advisories. Historical initial high/critical matches and their remediation remain in the Phase8 report; no current-image finding counts or resolution claims are invented. No new speculative application dependency update or finding waiver was made without valid results.

Cache policy is explicit: official provenance, validated cache hash on scan startup, DB built at most48hours ago (allowing5minutes clock skew), `--fail-on high` including critical, no suppression/`only-fixed` shortcut. Auto-update may be off only to scan with a prevalidated fresh cache; missing/stale/untrusted/empty error output blocks. Four new regression cases cover stale/invalid DBs, transfer/empty/malformed output, untrusted provenance and high findings despite process success. Review any eventual false-positive justification individually; none is asserted here.

Next executable local action after network recovery, using the catalog's official checksum-pinned URL:

```powershell
docker run --rm -e GRYPE_DB_CACHE_DIR=/cache -e GRYPE_DB_UPDATE_DOWNLOAD_TIMEOUT=90s -v ppi_phase8_security_cache:/cache anchore/grype:v0.120.1 db import '<official-fresh-catalog-URL>?checksum=sha256:<verified-catalog-checksum>'
.venv/Scripts/python.exe scripts/release_scan.py --directory artifacts/phase8-final --output artifacts/<new-scan-evidence-directory>
```

Refresh the official catalog/date before using a later archive; never weaken the48-hour policy to reuse stale data. The prepared CI separately scans built core/SDK/frontend and immutable infrastructure references, retains raw JSON/image identity artifacts on failure, and preserves blocking thresholds.

References consulted: [Grype configuration/freshness/hash controls](https://oss.anchore.com/docs/reference/grype/configuration/), [official checksum import command](https://oss.anchore.com/docs/reference/grype/cli/), [database publication/provenance](https://oss.anchore.com/docs/architecture/grype-db/). No alternate mirror was invented.

## D. Real browser acceptance

Final command: `P scripts/browser_acceptance.py --directory artifacts/phase8-final --output artifacts/phase8b-browser-final`, after `docker build -t ppi-phase8b-browser browser-tests`; `P` means `.venv/Scripts/python.exe`. A real non-root Chromium process runs with **sandbox enabled**, the official version-pinned seccomp profile and bounded memory/shared memory. Only the synthetic environment's public CA is imported into that disposable container's NSS store. Host/OS trust is unchanged, certificate errors are **not ignored**, and no security-warning interstitial is bypassed. The ordinary in-app browser's private-CA rejection is retained as a separate observation. Local `edge` SAN matches the test URL; no public TLS deployment is claimed.

The passing journey used actual rendered forms for login/org selection, new product/packaging, supported CSV and unsupported-file error, real clean scanning/visible status, positive private-source download with exact byte comparison, recorded candidate extraction and visible exact source quote, explicit owner review/canonical selection/application, reported dimensional claims, equipment context and four documented rules/activation. It produced **compatible**, **indeterminate for conflicting evidence**, **incompatible**, and **indeterminate for missing evidence**, using actual enums. The earlier compatible assessment's complete API representation remained identical after competing claims/rule changes; its UI historical snapshot and explanations were visually inspected in the retained screenshot. Reload verified product/packaging persistence.

The browser also switched to an empty second tenant and verified no stale catalog, demonstrated member review controls absent and real unauthorized review403, foreign/guessed record/file404, revoked membership UI/file404 and logout403. API-only membership management was explicit supporting setup through normal owner session/CSRF, not a substitute for the UI business journey. No direct DB edits, `force_authenticate`, disabled scanner or live provider made it pass. The exact `synthetic_rehearsal_only` guard runs before extraction. New synthetic tenants preserve the original Phase8 recovery fixture.

Earlier runs are retained: run1 failed an overly exact label locator after passing TLS/login/product; run2 saw a valid upload return400 after≈5.5s and its short URL assertion failed, with the precise transient cause unestablished; later real-scanner uploads succeeded unchanged. Run3 omitted the required equipment operational context and activation correctly returned400. Run4's test tried reading an upload response body after the UI had navigated away. Corrected accessible combobox/scoped picker locators, complete synthetic specifications, explicit response/status waits and response lifetime handling passed run5. The final run adds positive download-byte and visible source-quote checks and passed in54.3s. These were harness/fixture corrections; **no application defect or compatibility-rule change was needed**. Scanner deadlines/fail-closed behavior were not relaxed.

Evidence: final `acceptance.json`, `execution.json`, JSON reporter (1 expected,0 unexpected), redacted `browser.log` and `compatible-history.png`. Traces/video/login screenshots are off; runner and driver redact synthetic passwords from text artifacts. An explicit scan of final text artifacts found none. This is desktop Chromium acceptance, not full accessibility, mobile, Firefox/WebKit or live-model quality certification. Existing PostgreSQL expiry/lease/cancel/duplicate tests remain supporting coverage.

## E. Hosted CI

Authenticated read-only connector inspections verified run metadata and every baseline job: `backend`, `frontend`, `compose-smoke`, `backend-images (false)` and `(true)` all **failure**, no runner name/steps. The connector could not fetch check annotations, so the public run summary was read in a real browser. Its annotations explicitly identify an **account billing lock preventing job startup**. This is an owner/account blocker, not evidence of application test failures. No billing action, rerun/dispatch or purchase was attempted. Sanitized evidence: `artifacts/phase8b-hosted.json`; [run summary](https://github.com/user1738mike/physical-product-intelligence/actions/runs/38893453197).

Prepared workflow now uses **Ubuntu24.04** explicitly after the run's notice of `ubuntu-latest` migrating to Ubuntu26 on October19; this avoids a silent host transition. It retains least-privilege `contents: read`, PostgreSQL/migrations/schema, frontend/build, script and mocked evaluation checks; adds exact PostgreSQL/nginx/ClamAV digest scans, scan/image identity artifact retention and real isolated HTTPS browser acceptance. Core/SDK and infrastructure matrices do not cancel sibling evidence on first failure. There are6 job definitions/9 expanded jobs. No production secret/OpenAI key is required. YAML parsed locally; no hosted execution of these uncommitted changes is claimed.

The user must resolve billing eligibility and authorize the proposed commit/push before exact-candidate hosted acceptance can close. Require success for the new SHA and inspect every failure/cancellation/skip; a run for2cdb78e does not cover this new work. Hosted app builds create new artifacts: record their IDs and scan results, promote those same artifacts where possible and verify any rebuilt/deployed artifacts separately. No uploaded artifact from a successful current-candidate hosted run exists yet.

## F. Deployment target

No real staging/production target or authorization was supplied/found. [The concrete target handoff](phase8b-target-handoff.md) covers the single existing architecture, owner/account/region/domain/exposure, measured-resource limitations, managed TLS PostgreSQL, private encrypted storage, real scanner, synchronous jobs, off-host backup/monitoring ownership, required secret names/secure external provisioning, recurring cost categories and missing budget decision.

`compose.host.yaml`, `deploy/nginx.host.conf.template`, `deploy/host-release.example.env` and `deploy/staging-target.example.json` finish reviewable configuration/commands. Required substitutions refuse missing values; the overlay has no DB/backend/scanner host ports, requires an explicit exposure interface/collision-checked subnet, narrows proxy trust to the reserved ingress/32, mounts DB CA separately and keeps AI disabled. Syntax was checked with synthetic inputs using `docker compose ... config --quiet` and non-root/read-only `nginx -t` with read-only rehearsal certificates. No host resources/network were provisioned by those syntax checks. Actual TLS, firewall, roles, storage/backup encryption, monitoring delivery, costs and endpoint validation remain blocked on target decisions. Staging and production approvals/evidence remain separate.

## G. Verification commands and preserved controls

| Check | Newly executed result / evidence |
| --- | --- |
| PostgreSQL full suite | **Passed202, zero skips,133.324s, exit0**. `docker run --rm --network ppi-rehearsal-1685df9267_default --env-file artifacts/phase8-final/migration.env -e POSTGRES_DB=ppi_phase8b_validation -e DJANGO_SETTINGS_MODULE=config.settings.test -e INGESTION_SCANNER= -e TRUSTED_PROXY_CIDRS= -v ppi-rehearsal-1685df9267_rehearsal_tls:/certs:ro --entrypoint python ppi-phase8-backend-sdk manage.py test accounts organizations operations products ingestion compatibility --noinput`; `artifacts/phase8b-backend-tests.log`. Separate newly created test DB only. |
| Backend consistency/config/migrations/schema/evaluation | **Passed** in the SDK image on the isolated network: `python -m pip check`, `manage.py check`, `makemigrations --check --dry-run`, `migrate --check`, `evaluate_extraction` (**18/18,0 calls**), inert `check_ai_provider`, `spectacular --validate --fail-on-warn --file /tmp/openapi.yaml`. `artifacts/phase8b-backend-checks.log`. |
| Frontend complete required commands | **Passed** offline in `ppi-phase8-frontend-tests`: `npm run format:check`, `lint`, `typecheck`, `test` (**37/8files**), `build`. `artifacts/phase8b-frontend-checks.log`. |
| Script/config/style | **Passed15**: `P -m unittest discover -s scripts -p 'test_*.py'`; `P scripts/check_production_config.py`; Ruff format/check using `backend/pyproject.toml`; browser Prettier and `node --check`; workflow YAML parse; `git diff --check`. |
| Browser | **Passed1 complete journey/8 checkpoints,54.3s**; exact command/evidence inD. Certificate validation/sandbox, source bytes, UI review and negatives all enforced. |
| Frontend advisory service | Native attempt **failed** socket hang-up; changed Linux execution attempt **passed**, `docker run --rm -e npm_config_fetch_retries=0 -e npm_config_fetch_timeout=30000 --entrypoint npm ppi-phase8-frontend-tests audit --json`; final209 dependency entries/zero reported vulnerabilities. |
| Grype DB/import/image acceptance | **Import failed / acceptance blocked**, no zero-finding substitute. `P scripts/release_scan.py --directory artifacts/phase8-final --output artifacts/phase8b-scans` inventoried7 exact artifacts and refused invalid DB. |
| Host syntax | **Passed** `docker compose --env-file artifacts/phase8b-host-check.env -p ppi-host-configuration-check -f compose.production.yaml -f compose.host.yaml config --quiet`; non-root/read-only nginx1.30.4 `-t` using `artifacts/phase8b-nginx-check.conf` and read-only rehearsal TLS volume. No deployment. |
| Existing recovery/load | **Retained, not rerun**; valid historical Phase8 evidence with original revision/environment and workload limits. |
| Live provider/customer documents | **Not applicable/prohibited**; zero live requests and no customer evidence used. |
| Real staging/production/public TLS/off-host monitoring/backups | **Blocked/documented but not executed**; no target/authorization. |

Existing `.env`/credentials, DBs/private files/volumes and unrelated applications/networks were preserved. Only new synthetic tenant records/test DBs and ephemeral validation/browser containers were used; no cleanup/prune/reset of existing Docker resources occurred. Browser fixture credentials travel on stdin, never build args/argv/env/commits; OpenAI credentials are never read/copied. Core production controls, role/tenant enforcement, scanner requirement and deterministic compatibility semantics remain unchanged.

## H. Git state and concrete next authorization

Current work is uncommitted/unstaged on `main`, baseline2cdb78e; no commit/push, registry publication or remote deployment was performed. Previous Phase8 files are already in the user's commit. Deliberate inclusion for this follow-up: `.github/workflows/ci.yml`, `browser-tests/` (locked tooling, official seccomp profile, runner/tests/docs), `scripts/{browser_acceptance,release_scan,test_release_scan}.py`, `compose.host.yaml`, the3 new host/target templates, this report/target handoff and Phase8 documentation follow-up links. There were no pre-existing user changes at start. Never stage `artifacts/`, `.env`, fixture credentials, certificates/private evidence or backups.

Proposed branch **codex/phase8b-release-gates**; proposed message **Close browser release acceptance and prepare remaining deployment gates**. After owner review and explicit authorization only:

```powershell
git switch -c codex/phase8b-release-gates
git add .github/workflows/ci.yml browser-tests scripts/browser_acceptance.py scripts/release_scan.py scripts/test_release_scan.py compose.host.yaml deploy/host-release.example.env deploy/nginx.host.conf.template deploy/staging-target.example.json docs/phase8b-release-closure-report.md docs/phase8b-target-handoff.md docs/phase8-completion-report.md docs/phase8-release-checklist.md docs/phase8-deployment-plan.md
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "Close browser release acceptance and prepare remaining deployment gates"
git push -u origin codex/phase8b-release-gates
git rev-parse HEAD
gh run list --repo user1738mike/physical-product-intelligence --workflow ci.yml --branch codex/phase8b-release-gates --commit <new-sha>
gh run view <new-run-id> --repo user1738mike/physical-product-intelligence --log-failed
```

Push automatically triggers the prepared workflow; do not additionally dispatch just to manufacture evidence. Owner must first resolve the observed GitHub billing lock without this task making a financial transaction. Once execution is eligible, require passing exact-SHA jobs and valid fresh scan results; triage blocking advisories. Separately provide approved host/account owner/access method, region/domain/exposure, budget and staging deployment authorization, provisioning secrets securely outside chat/repository. The target handoff provides the exact remaining deployment/verification sequence.

**Decision:** local functional/browser checks complete; exact-candidate hosted CI **not passed**; staging **not validated**; **not ready for production release**; no remote deployment. Phase8 is not declared released, and no Phase9 work is included. The remaining blockers are specifically environment/account/authorization decisions and unavailable vulnerability evidence, not a newly established application security/compatibility defect.
