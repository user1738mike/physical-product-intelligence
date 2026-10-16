# Phase 8 release checklist

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
