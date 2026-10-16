# Phase 8 deployment plan

This is one Docker Compose path: `compose.production.yaml` is the application base; `compose.rehearsal.yaml` adds isolated local TLS/PostgreSQL/ClamAV/ingress for rehearsal. No hosting account, Linux server, production domain, budget or deployment authorization is assumed. Local rehearsal is authorized; remote cutover, DNS, image publication and Git mutations require separate authorization.

## Capability reconciliation

| Roadmap capability | Implemented scope | Remaining / commercial boundary |
| --- | --- | --- |
| Identity and tenancy | Session/CSRF login/logout, organization selection, owner/admin/member roles, revocation, tenant isolation and audit | No recovery email, invitations, verified-email, MFA/SSO; pilot operator onboarding/recovery process must be agreed |
| Products and packaging | Tenant catalog, versioned packaging profiles, exact units, competing claims and immutable histories | No automatic physical validation/certification |
| Evidence ingestion and processing | Private bounded CSV/XLSX/TXT/text-PDF, validation, scanner hook, deterministic parsing and durable job/review state | No OCR/vision; scanner/storage/retention must be provisioned and operated |
| Human review and canonical claims | Explicit approval/correction, reported provenance, selection and guarded transactional apply | AI cannot approve/select itself or create physical verification |
| Equipment and assessments | Versioned specifications/rules, deterministic captured-input results/explanations and immutable snapshots | Recorded constraints are not hardware safety certification |
| AI extraction | Optional configurable adapter and mocked/recorded synthetic orchestration, strict grounding/schema | No Phase 8 live requests; live quality/account/latency not established |
| APIs and UI | Tenant-scoped APIs plus catalog/import/equipment/assessment workspaces | API/proxy checks and rendered tests do not substitute for full manual accessibility/device acceptance |
| Operations | Shared DB admission, leases/retries, strict production settings, diagnostics, private recovery and release rehearsal | Single-host filesystem, manual interrupted-job recovery; external infrastructure/hosted CI gates remain |
| Commercial capabilities | No subscriptions, entitlement engine, commercial usage ledger or billing integration found | Separate product gap; do not infer completion from Phase 8 or add a billing platform here |

A controlled private pilot needs explicit participant access control, terms, privacy/evidence policy, support/recovery ownership and an **agreed manual commercial process**. Agreement is a gate, not an assumption. Paid public launch additionally needs reviewed subscriptions/entitlements/metering/billing, commercial abuse/lifecycle controls and customer account recovery. Registration throttles are not entitlements. Do not advertise automated billing or paid self-service launch.

## Topology and boundaries

Local entry is CA-verified `https://127.0.0.1:18443`. Nginx runs non-root on internal 8443, serves TLS, sends `/api/v1/` directly to Django and other paths to standalone Next. It strips spoofable forwarding headers and sets canonical scheme/client address. Backend trusts only the edge's selected /32 IP. Next's fallback uses internal HTTPS edge with the rehearsal CA. No backend, DB or scanner port is published. Existing applications on 3000/8001/8443 are preserved.

Rehearsal PostgreSQL 17 uses TLS with hostname validation, an isolated database and separate migration/admin versus non-owner runtime DML roles. Private evidence, DB, backup/restore data, scanner signatures and TLS keys have separate persistent named volumes. Only the public CA is exported. Application images run non-root/read-only; nginx temporary directories live on bounded tmpfs. Official ClamAV is real, private and fail-closed; its signature availability/freshness is separate evidence from an adapter mock. Backend readiness probes the required scanner, not merely a nonempty scanner setting. Optional disabled AI is not a dependency of normal readiness.

The recorded extraction adapter exists only in explicit `config.settings.rehearsal` with a synthetic-only marker and rehearsal database identity. Production settings cannot enable it via provider name. It performs no network/credential/SDK access. Never use rehearsal settings for customers. Normal production AI remains disabled unless separately reviewed; **Phase 8 prohibits live AI calls**.

Resource assumptions: a Linux amd64 host with Docker/Compose, SSD-backed encrypted persistent storage, provisionally 4+ vCPU/8 GiB for a small pilot, separately measured on the actual host. Rehearsal records the VM's real resources and co-running workloads. Backend cap 1 GiB/2 CPU, frontend 768 MiB/1 CPU, scanner 3 GiB/2 CPU, DB 512 MiB and ingress 128 MiB; these are starting bounds, not supported-scale claims. Filesystem deployment supports one host. Multi-host requires a tested shared/private storage adaptation. Jobs remain explicitly synchronous, leased and bounded; no worker/queue is invented.

## Reproducible preparation

Use the existing `.venv` Python driver locally, or an operator Python 3.13 environment. Build from locks. Python/Node security patch versions are recorded in Dockerfiles/CI; application/framework major versions are preserved. Images receive OS security updates during build, then are referenced by exact local SHA-256 identity in the release manifest. Production promotion must publish/transfer those exact reviewed artifacts after authorization, never rebuild behind a reused tag.

```powershell
# Build production backend and standalone frontend without touching the existing .env:
docker build -t physical-product-intelligence-backend backend
docker build --target production -t physical-product-intelligence-frontend frontend
docker pull postgres:17.11-bookworm
docker pull nginx:1.30.4
docker pull clamav/clamav:stable
python scripts/release.py prepare --directory artifacts/<new-release> --https-port 18443
python scripts/release.py start --directory artifacts/<new-release>
```

Moving dependency tags are resolved to immutable SHA identities at preparation; the manifest is the authority for the artifacts actually used. Do not claim a tag alone is immutable. Preparation refuses existing destinations/occupied ports, inventories routes/IPAM and selects a collision-free project subnet. It generates **only synthetic local DB/Django/TLS secrets**, never an OpenAI key; it neither reads nor overwrites root `.env`. It exports no private TLS keys. On Windows, generated mode bits are not proof of a private ACL; use an operator-only workspace and validate ACL/encryption before any real secrets/data. Production secret files belong outside the repository.

`release.json` records baseline revision, dirty flag, working-tree fingerprint, lock hashes, immutable image identities/build times, target and outcome journal. A dirty build is an identified local rehearsal, not a committed release and not verified by an old hosted run. Final `seal` preserves the rollout source snapshot and separately records the final reviewed source fingerprint and hashes of selected verification receipts; no commit/push is performed. Sensitive env/fixture/backup files remain ignored; publish only a reviewed sanitized manifest and aggregate reports, never the whole artifacts folder.

## Controlled release sequence

1. Preflight exact target/project/DB/image identity, protected settings, route/port inventory, dependencies and source/CI evidence. `scripts/release_preflight.py` is read-only and fails closed on missing target, authorization, clean commit, immutable artifacts, commercial decision or hosted evidence. It never reads secret contents or deploys remotely.
2. Announce/approve the maintenance window with the actual operator process (no notification is sent by this task). Stop only that target's edge/frontend/backend to quiesce writes; keep DB/private storage/scanner available. No zero-downtime claim.
3. `release.py backup` runs existing `backup_bundle` with matching installed PostgreSQL client and protected DB/private-file consistency window. Preserve and encrypt/off-host the bundle under the approved retention policy. A local named volume is not an off-host backup.
4. Apply forward migrations once through `release_migrate --confirm-database <exact_name>`. PostgreSQL advisory lock rejects concurrent migration owners; controller's exclusive file lock rejects overlapping host deployments. This is a single-host deployment path; do not claim a filesystem lock coordinates independent hosts. Review migration SQL/compatibility separately; no down-migrations or destructive restore occurs automatically.
5. `release.py rollout` requires a completed backup, updates the candidate backend image, starts production server containers, recreates ingress to refresh upstream addressing, awaits actual HTTPS ingress health and checks runtime identity/private bytes/immutable snapshots/tenant boundaries. Migration credentials are confined to the profiled job.
6. Run HTTPS session/user workflows, security dependency/failure probes, bounded load and observation. Record timestamps, exact artifacts and failures. Determine release acceptance; do not promote based only on a successful `up`.

```powershell
python scripts/release.py backup --directory artifacts/<release>
python scripts/release.py rollout --directory artifacts/<release>
python scripts/release.py verify --directory artifacts/<release>
python scripts/release.py status --directory artifacts/<release>
python scripts/release.py seal --directory artifacts/<release>
```

The driver deliberately has no remote transport or publication action and refuses non-rehearsal target identities. For an authorized Linux deployment, use the same production application base with the operator-provisioned TLS ingress/ClamAV/private volume and managed TLS PostgreSQL described in the operations guide. Inject separate `PPI_PRODUCTION_ENV_FILE` and `PPI_MIGRATION_ENV_FILE`, exact image digests, CA mount and approved origin. Run `docker compose --env-file <protected-release-variables> -p <approved-project> -f compose.production.yaml config --quiet`, the profiled `migration` job for backup/migration, then approved application rollout/readiness/smoke/observation. **Do not copy rehearsal fixture settings, local certificates, credentials or DB volume into production.** The external ingress/scanner/CA mounts must be reviewed for the specified host before applying; base recipe alone does not provision them.

Missing for a real deployment: authorized host/access, domain/DNS ownership and certificate policy, region/data residency, managed DB endpoint/CA and role grants, encrypted persistent/off-host backup locations, scanner lifecycle, network/firewall/trusted edge address, image registry/transfer approval, operational ownership, agreed pilot/commercial mode and exact candidate's hosted CI. Do not purchase or infer a free tier.

## Recovery and rollback

`release.py restore` requires a completed quiesced bundle and creates a **new empty isolated `ppi_restore_…` DB and new private root**. Existing bundle guards/checks compare model counts and private checksums, then real login/CSRF probes under runtime DML grants verify source access, immutable assessments and revoked/foreign denial. Original and restored DB/files remain preserved; no target is promoted automatically. Configuration/CA/roles/private bytes are necessary recovery inputs, not just a SQL dump. Keep encrypted off-host copies of protected configuration and keys under separate access/retention controls; do not include plaintext secrets in the sanitized manifest.

```powershell
python scripts/release.py restore --directory artifacts/<release>
python scripts/release.py rollback --directory artifacts/<release> --previous-image sha256:<reviewed_previous_image_id>
python scripts/release.py rollout --directory artifacts/<release>
```

Rollback requires a completed backup and explicit immutable prior artifact. It changes application image/settings only, performs **no reverse migration**, retains the candidate's controlled migration/recovery tools and verifies previous code against the resulting schema and private snapshots. The Phase 7 prior application does not contain rehearsal fixture settings, so its rollback uses strict production settings with AI disabled. Test both directions on the isolated environment before considering a real release. Incompatible schema requires a forward fix or separately approved isolated recovery/promotion, with explicit potential data loss; never restore over a live DB automatically.

## Verification and signals

Set `PPI_SMOKE_ORIGIN` to the local HTTPS origin and `PPI_SMOKE_CA` to that rehearsal's exported public CA. Run existing Phase 2 and Phase 3 smoke with `--allow-create-test-data`; set `PPI_SMOKE_FIXTURES=recorded` and `PPI_REHEARSAL_CONTEXT=<protected-artifact-path>` for the recorded extraction journey. This context contains only synthetic fixture credentials and must remain private/ignored. Tests obtain normal CSRF/session authorization and invoke real services; no manual DB edits make the journey pass. Rendering tests remain separate from browser attachment/manual visual acceptance.

`release_probes.py --load` declares 240 authenticated product reads, concurrency 4, maximum 30 seconds, provisional p95 ≤1500 ms and zero errors before running; it records actual completed requests, p50/p95/p99, throughput, time, resources and job state. It is a small local pilot test, not a load/SLO/scale promise. Run only on this loopback rehearsal or a separately authorized target; compare actual host/resource contention. Existing PostgreSQL regressions cover lease interruption, retries/cancellation and duplicate persistence; the journey also repeats a start UUID.

`release_security.py` exercises real EICAR rejection, temporarily stops only the rehearsal scanner, verifies readiness 503/liveness 200 and rejected uploads, then restores scanning in a finally block and captures a redacted correlation/failure signal. It contacts nobody. JSON request/audit logs plus readiness, operator job state/age, scanner and DB metrics provide local signals; production must provision log retention, collectors/alerts/on-call ownership and validate delivery separately. No achieved SLO, off-host monitoring or incident notification is claimed.

## Official references consulted

- [Docker Compose production](https://docs.docker.com/compose/how-tos/production/) and [service/image/health policies](https://docs.docker.com/reference/compose-file/services/).
- [Official ClamAV Docker/signature/health guidance](https://docs.clamav.net/manual/Installing/Docker.html).
- [Nginx proxy header behavior](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
- Installed Next.js 16.4.0 self-hosting/deployment guides under `frontend/node_modules/next/dist/docs/01-app/` were read before Docker changes.
- [Python 3.13.16 security maintenance release](https://www.python.org/downloads/release/python-31316/), [official Node release metadata](https://nodejs.org/dist/index.json), and [Debian security advisories](https://security-tracker.debian.org/tracker/) informed patch remediation. A version selection alone is not a passing rescan.

See [release checklist](phase8-release-checklist.md), [completion report](phase8-completion-report.md) and the maintained [operations guide](deployment-and-operations.md) for actual outcomes and unverified gates.
