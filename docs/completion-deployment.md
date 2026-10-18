# Completion candidate deployment and operator handoff

This is the current handoff; historical Phase8B reports describe earlier inputs.
Plans, entitlements, metering, provider-independent billing and customer
integrations are implemented. Real payment collection still needs the grounded
merchant/provider/commercial decisions and a sandbox-verified concrete adapter.
No host, domain, region, budget, registry publication or remote deployment is
authorized or provisioned by this completion work.

The supported topology remains one Linux Docker/Compose host, persistent private
filesystem storage, a separately protected PostgreSQL connection and TLS ingress.
No broker or Kubernetes is required. Existing4vCPU/8GiB host sizing is provisional,
with managed DB separate; qualify the actual target. Backend/frontend/scanner/
edge limits plus two512MiB/1CPU processor services and host overhead must fit.
Local rehearsal has additional unrelated stacks; report measured contention and
read-workload results without extrapolating extraction/write/customer capacity.

Before deployment: passing exact-artifact vulnerability acceptance, exact-SHA
hosted jobs, approved staging host/domain/region/exposure/budget and deployment
authorization. Fill an external copy of `deploy/staging-target.example.json`.
Provision required env files, database CA and TLS/signing material outside Git via
the existing secure host/vault process. Never send secrets in chat or copy the
repository env or synthetic rehearsal files. Production stays AI-disabled;
normal tests use mocked responses. Live AI or real payment requests need their
specific authorization and approved data boundary.

Build supported images with the tracked backend/frontend Dockerfiles and
`deploy/ingress.Dockerfile`. Record every resulting immutable identity and scan
it; a rebuild is not the previously verified artifact. The production frontend
starts node directly and intentionally omits runtime npm. Promotion/transport of
the same accepted archives is preferable after publication/deployment is
authorized; no image has been published by this task.

The prepared host composition is:

```sh
docker compose --env-file /etc/ppi/compose.env \
  -f compose.production.yaml -f compose.processors.yaml \
  -f compose.host.yaml -f compose.processors.host.yaml config --quiet
```

Set immutable PPI backend/frontend/ingress/scanner references, protected runtime
and migration env paths, approved DB CA path, trusted ingress addresses and TLS
paths using the existing host overlay contract. Migration/processor configuration
uses the protected owner connection; HTTP uses its narrow runtime DML role with
no ownership, elevated role inheritance or public schema creation. Apply controlled
migrations, review new default grants, and validate readiness and actual HTTP
denials. Do not give customers a staff or database-owner shortcut.

Provision a dedicated active staff operator with an unusable password through the
trusted owner-only administrative session. Refuse reuse/elevation of an ordinary
customer account; give it no tenant membership. Set PPI_PROCESSOR_ACTOR to that
non-secret username. Maintenance and billing use separate supervised services,
read-only root filesystems, tmpfs heartbeats, bounded cycles and restart policies.
The maintenance worker alone receives private evidence storage. Billing has no
file/backup mount and defaults disabled; enabling it cannot create/resubmit charges
or make the presently unavailable real provider work.

Read [processor operations](processor-operations.md),
[billing lifecycle](billing-processor-operations.md),
[source retention](source-retention.md) and [recovery](account-recovery.md).
Approve actual legal retention, hold authority, backup retention/erasure and
incident ownership. Defaults preserve sources; owner requests never purge
canonical/applied evidence, statements or audit history. An uncertain filesystem
removal blocks hold confirmation/backup acceptance until quiesced reconciliation.
Historical backups may contain later-removed bytes and need their separate policy.

Monitor the actual host: HTTPS readiness and liveness, processor heartbeat/health,
redacted failure counts, extraction age/reservations, delivery due/retry/dead-letter
state, billing uncertain/inbox backlogs, source-removal queued age/needs_review,
scanner/signature health, DB failures, disk pressure and backup age/restore failures.
`python manage.py operational_status` exposes fixed aggregate state counts without
provider bodies or secrets. Alert immediately on uncertain removal, unhealthy
worker or failed backup; investigate stale billing without resubmitting payments.
Validate alert routing when recipients and monitoring are approved; this task does
not send messages or provision a monitoring account.

Maintenance must quiesce all writers, including both processors, before DB/private
backup. Restore into a new empty isolated database and new private root, verify
counts/hash/removal history and then apply controlled forward migrations. No
working DB, volume or prior bundle is overwritten. Test recovery and monitor the
original source byte hash and immutable assessment snapshots.

Local rehearsal commands prepared for the current generated target:

```sh
python scripts/release.py backup --directory artifacts/completion-patched-rehearsal
python scripts/release.py restore --directory artifacts/completion-patched-rehearsal
python scripts/release.py rollback --directory artifacts/completion-patched-rehearsal \
  --previous-image sha256:0a0d1caa3eae7f77da2fff88d2867c1ab64645bfa54783c5d882e691d0d21a84 \
  --previous-frontend-image sha256:eeca9c22bdf334e140bbd0be617582d83eae64a839ab80dbe50bf54b572c1c2f
python scripts/release.py rollout --directory artifacts/completion-patched-rehearsal
```

Rollback explicitly pairs the prior billing backend with its identity application
on the patched supported Node runtime (2181 identical application files/symlinks),
retains forward DB guards/history and keeps trusted recovery/processor tools on
the candidate. The old Phase8 artifact is not an approved rollback: it lacks newer
commercial/integration enforcement. Scan acceptance for both selected rollback
images remains required; local functional compatibility does not waive findings.
The commands above concern only generated loopback rehearsal state, never SSH or
the eventual staging/production target.

Staging validation must repeat real endpoint/browser tenant/role/file/integration
checks, configured egress, supervised recovery, target-specific load and backup/
restore/rollback with the promoted artifacts. Production verification and paid
commercial readiness are separate gates. No deployment or readiness claim follows
from a prepared template, simulator receipt or successful local build.
