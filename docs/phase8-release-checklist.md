# Phase 8 release checklist

## Phase 10 candidate gates

- Rebuild/identify the current integration-enabled artifacts; do not apply earlier scan, hosted CI or browser evidence to changed images.
- Verify credential issuer revocation, finite plan policy, shared admission and immutable export fidelity on the exact target.
- Provision a dedicated versioned signing root securely only after approval; approve exact destination hosts and isolated egress/DNS/firewall controls. Test real outbound TLS and receiver coordination on approved staging.
- Verify runtime integration grants and append-only protections, restricted dispatcher owner connection, bounded cadence, retention/legal hold and backup/restore under target roles.
- Retain valid Grype database/scans, exact-SHA hosted CI, approved staging host/domain/region/budget, payment-provider verification and live collection gates. Local loopback delivery is not real customer destination acceptance.
- Use [Phase 10 actual results](phase10-completion-report.md) and [delivery operations](webhook-delivery.md); no production deployment is approved.

## Phase 9B candidate

- [ ] Publish only after separate authorization and obtain passing exact-SHA hosted CI.
- [ ] Obtain fresh valid Grype results for the new images; no earlier image acceptance transfers.
- [ ] Approve target/domain/region/budget and validate staging migrations, runtime grants, tenant and financial flows.
- [ ] Before real collection: select/approve provider and merchant account, commercial/currency/tax/refund/grace policy, official adapter verification and separately authorized sandbox testing.

Local simulator results are distinguished from real collection in [the Phase 9B report](phase9b-completion-report.md). No production release is declared.

## Phase 9A candidate

- [ ] Obtain passing exact-candidate hosted CI after the account billing lock is resolved.
- [ ] Obtain acceptable fresh Grype DB and assess the new Phase 9A images; old images/results cannot clear this gate.
- [ ] Approve staging host/domain/region/exposure/budget, separately authorize deployment, then validate migrations, exact runtime grants and commercial/tenant/browser flows.

Phase 9A local verification and new artifact identities are recorded in [its report](phase9a-completion-report.md). Historical Phase 8/8B manifests remain unchanged. Manual plan assignments and usage accounting do not implement payment collection or approve commercial launch.

## Phase 8B follow-up — 2026-10-16

- [x] Reconcile the user's subsequent clean Phase8 commit2cdb78e with the retained dirty-build manifest and verify prior receipt hashes.
- [x] Complete a real sandboxed Chromium journey through private-CA-verified HTTPS, including download byte integrity, reviewed extraction, all assessment outcomes and tenant/role/revocation/logout denials.
- [x] Run202 backend/37 frontend/15 script tests and18 mocked evaluation cases; check migrations/schema, full frontend build and deployment syntax.
- [x] Obtain a current frontend npm advisory result in the Linux runtime: zero reported findings; preserve the earlier native network failure separately.
- [x] Diagnose hosted startup failure from GitHub's visible annotations: account billing lock; no billing changes made.
- [x] Prepare one host overlay, protected configuration templates, exact deployment commands and a narrowly scoped proposed commit/push handoff.
- [ ] Obtain valid fresh official Grype DB and passing reviewed image/backend dependency results; current seven-image inventory remains blocked.
- [ ] Owner resolves the GitHub billing lock, authorizes publishing the reviewed Phase8B candidate, and verifies all exact-SHA hosted jobs.
- [ ] Approve/provision the specific staging host/domain/region/exposure/budget and external secrets; execute separate staging acceptance before any production decision.

See [the closure report](phase8b-release-closure-report.md) and [target handoff](phase8b-target-handoff.md). Local browser success does not check the actual staging/public TLS endpoint. Historical Phase8 checklist items below retain their original scope; unmet promotion gates remain required.

Use this with the [deployment plan](phase8-deployment-plan.md), [actual report](phase8-completion-report.md) and [operations guide](deployment-and-operations.md). Checked items below concern the synthetic local rehearsal only. They do not approve a customer deployment.

## Local evidence

- [x] Audit actual code, historical Phase 5–7 claims and commercial gaps.
- [x] Preserve existing `.env`, applications, databases, networks and volumes.
- [x] Separate strict production settings, CA-verified HTTPS and PostgreSQL, narrow proxy trust and non-owner runtime role.
- [x] Run real ClamAV clean/infected/unavailable checks, with fail-closed upload behavior and readiness recovery.
- [x] Exercise real session/CSRF authentication, roles, tenant/private-file denials, human-reviewed recorded extraction and deterministic assessments.
- [x] Quiesce and back up database plus private bytes; restore to a new isolated target; verify permissions and historical snapshots.
- [x] Test prior application against current schema, without reverse migrations, then return to the patched candidate.
- [x] Record immutable image identities, lock hashes, dirty source identity and outcome journal in `artifacts/phase8-final/release.json`.
- [ ] Accept final vulnerability results: all required artifacts must have passing, reviewed evidence; no implicit waiver.
- [x] Complete final functional checks/load/restart/observation; consult the report for separate failed/blocked security gates.

## Promotion gates — all remain required

- [ ] Human review and separately authorized commit/push of the completed candidate; no secrets/artifacts/private fixture files staged.
- [ ] Successful hosted `ci.yml` for that exact committed SHA, including image vulnerability gates and SDK mocks. Resolve failures rather than suppressing them.
- [ ] Publish/transfer the exact approved image identities only after authorization. Preserve a compatible reviewed rollback artifact.
- [ ] Explicit staging/production host, access, domain/DNS/TLS policy, region, budget and deployment authorization.
- [ ] Provision external secret files, DB CA and roles, trusted ingress address, private encrypted persistent storage and current scanner.
- [ ] Approved manual private-pilot commercial/access process, or separately implemented subscriptions, entitlements, usage metering and billing before paid public launch.
- [ ] Agree account onboarding/recovery, evidence retention/privacy, support, incident owner and maintenance window.
- [ ] Verify host-specific ingress, browser/device/accessibility journey, abuse limits and resource capacity.
- [ ] Encrypt and copy backups off-host; validate retention, recovery access, representative restore and realistic recovery objectives.
- [ ] Validate retained logs, monitoring delivery/alerts and an operational response procedure on the actual target.
- [ ] Keep AI disabled unless separately approved after Phase 8; this phase permits no live provider requests.

## Concrete next sequence

1. Resolve any local failed security gates in the report; review changes and proposed target. Do not use the rehearsal fixture settings/credentials/certificates for customer data.
2. After separately authorized commit/push, inspect `gh run list --repo user1738mike/physical-product-intelligence --workflow ci.yml --branch main`, then `gh run view <id> --repo user1738mike/physical-product-intelligence`. Require exact SHA, completed/success and reviewed scan findings.
3. Fill an external copy of `deploy/production-target.example.json` with approved host/origin/commercial mode and protected external file paths. Run `python scripts/release_preflight.py --target <external-target.json> --manifest <reviewed-release.json> --verify-hosted`. A pass is preflight only, not infrastructure acceptance or deployment permission.
4. Use the plan's exact production Compose/config/backup/migration/rollout sequence in the approved maintenance window. Verify HTTPS readiness, tenant journey, private bytes, scanning and observation on staging before a production decision.
5. Record separate repository, staging, release and deployed decisions. Never promote an isolated restore automatically or run destructive reverse migrations.
