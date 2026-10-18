# Single-host staging handoff

This prepares the existing Linux-host architecture; it does not allocate or authorize a target. Start from an existing approved Linux host with Docker/Compose and a separately provisioned, certificate-verified PostgreSQL database. No provider, region, account entitlement, DNS ownership or budget is assumed.

## Owner decisions required

Provide host/account owner and access method, region/data residency, approved staging hostname, private exposure policy (VPN/allowlist or explicitly approved interface), budget cap and deployment authorization. Fill an external copy of `deploy/staging-target.example.json`. Do not paste passwords, API keys or private certificates into chat. A controlled private pilot additionally needs an approved manual onboarding/commercial/support process; paid public subscriptions/entitlements/metering/billing remain unimplemented.

Provisionally reserve 4 vCPU, 8 GiB RAM and encrypted SSD storage; validate on that actual host. The retained rehearsal used an 8-CPU/7.6-GiB Docker VM and a small read workload, not an extraction/write saturation benchmark. Application caps are backend1GiB/2CPU, frontend768MiB/1CPU, scanner3GiB/2CPU, edge128MiB; managed PostgreSQL is separate. No queue/worker is introduced: jobs are synchronous, leased and bounded. A second instance/shared storage is outside this tested filesystem deployment.

Recurring cost items requiring approval: host/SSD and snapshots, managed DB/storage/backups, domain/certificate operation, encrypted off-host backup retention/egress, signature downloads, monitoring/log retention and CI/registry storage/execution. No price/free-tier claim or purchase is made. Reuse suitable existing infrastructure after its owner approves capacity, isolation and cost.

## Protected configuration

Use operator-controlled secret provisioning on the host or its existing vault. Root-readable runtime/migration env files live outside the checkout, normally `/etc/ppi/runtime.env` and `/etc/ppi/migration.env`, mode0600; no repository `.env` is copied. Required names: `DJANGO_SECRET_KEY`, exact `DJANGO_ALLOWED_HOSTS`, HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS`, `POSTGRES_DB/USER/PASSWORD/HOST/PORT`; migration uses its separate administrative identity. `POSTGRES_SSLROOTCERT` is mounted at `/certs/database-ca.crt` with hostname validation. Apply reviewed runtime DML/default grants after migrations, with no ownership/elevated role inheritance; production readiness refuses privileged runtime identity. Use the existing operations guide for grants and database provenance triggers.

AI stays disabled in this host overlay. Do not provision/copy an OpenAI key for Phase 8B or execute a live provider command. Existing secure key configuration is unchanged. Private evidence, scanner signatures and protected recovery bundles use dedicated persistent volumes; host encryption/access controls and encrypted off-host copies remain required. Agree evidence/backup retention, legal hold, incident owner, restore access and monitoring/alert delivery before customer use.

Provision public TLS full chain as `/etc/ppi/tls/edge.crt` and private key as `edge.key`, readable only by ingress UID101. The directory can be root:101 mode0750; private key UID101 mode0600, public chain0644. Mount the managed DB CA separately; never mount a directory of secret env files into ingress. Set approved firewall/VPN restrictions before exposure; DB/backend/scanner receive no host ports.

## Exact authorized-host sequence

Commands below are prepared, **not executed remotely**. Run from the reviewed checkout on the approved host, with verified loaded application artifacts and passing exact-SHA hosted evidence. Populate an external `/etc/ppi/release.env` from `deploy/host-release.example.env`; all placeholder/interface/subnet/digest values require review. Use `scripts/compose_network.py` against that host's actual routes/IPAM to select a collision-free subnet and reserve the edge IP; do not copy this workstation's subnet. Pin registry infrastructure digests and loaded application IDs to the artifacts actually scanned. Transfer/load approved artifacts only after authorization; verify archive checksums first. A new build is a new artifact and must be verified.

```sh
# Render only the domain token; leave nginx's own $host/$remote_addr variables intact.
export PPI_DOMAIN='<approved-exact-hostname>'
envsubst '${PPI_DOMAIN}' < deploy/nginx.host.conf.template > /etc/ppi/nginx.conf
# Acquire one host deployment owner. Migration additionally takes a DB advisory lock.
flock -n /var/lock/ppi-release.lock bash
docker compose --env-file /etc/ppi/release.env -p ppi-staging -f compose.production.yaml -f compose.host.yaml config --quiet
docker compose --env-file /etc/ppi/release.env -p ppi-staging -f compose.production.yaml -f compose.host.yaml up -d --wait --wait-timeout 480 scanner
# Announced maintenance window: quiesce application writers only.
docker compose --env-file /etc/ppi/release.env -p ppi-staging -f compose.production.yaml -f compose.host.yaml stop edge frontend backend
docker compose --env-file /etc/ppi/release.env -p ppi-staging -f compose.production.yaml -f compose.host.yaml run --rm --no-deps migration python manage.py backup_bundle --maintenance-window --confirm-database '<approved-db-name>' --output '/var/lib/ppi/backups/<new-exclusive-release-id>'
docker compose --env-file /etc/ppi/release.env -p ppi-staging -f compose.production.yaml -f compose.host.yaml run --rm --no-deps migration python manage.py release_migrate --confirm-database '<approved-db-name>'
# Operator applies reviewed runtime grants for new migration objects here, then validates them.
docker compose --env-file /etc/ppi/release.env -p ppi-staging -f compose.production.yaml -f compose.host.yaml up -d --no-deps --wait --wait-timeout 180 backend frontend
docker compose --env-file /etc/ppi/release.env -p ppi-staging -f compose.production.yaml -f compose.host.yaml up -d --no-deps --force-recreate --wait --wait-timeout 120 edge
curl --fail --show-error "https://${PPI_DOMAIN}/api/v1/health/ready/"
docker compose --env-file /etc/ppi/release.env -p ppi-staging -f compose.production.yaml -f compose.host.yaml exec -T backend python manage.py operational_status
exit # releases host flock shell
```

Before the backup command on a new empty installation, initialize its schema through the controlled migration step and review the first-install plan; do not manufacture a backup of a nonexistent schema. For an existing installation, backup precedes forward migration. Keep protected configuration/CA/key recovery and encrypted off-host bundle copies as separate controlled recovery inputs.

Then run real staging browser/session/tenant/private-file/real-scanner checks and bounded observation with approved synthetic identities. Use actual staging certificate trust, no rehearsal fixture provider or certificate bypass. Deterministic fixtures belong only in an isolated non-customer test environment; staging AI remains disabled unless a separately reviewed synthetic provider strategy is approved. Do not run the synthetic DB bootstrap/access commands against a real deployment: they intentionally reject working database names. Record URL, source SHA, deployed image identities, timestamp, schema state and results. A healthy `up` alone is not acceptance.

If readiness/security/tenant checks fail, stop cutover, preserve DB/files and inspect redacted logs. Restore the reviewed compatible prior application artifact only when its current-schema compatibility and security gate passed. Do not reverse migrations or restore over the live DB. Incompatible schema needs a forward fix or a separately authorized isolated restore/promotion with an explicit data-loss decision. Prior Phase 8 compatibility evidence is local evidence only, and its older artifact lacks passing vulnerability acceptance.

Monitoring must retain sanitized request/error/correlation logs, readiness, DB failures, job state/age, admission limits, scanner health/signatures, storage pressure and backup/restore failures. Validate delivery and the response procedure without contacting other people from this task. Staging and production require separate approvals and evidence; this handoff approves neither.
