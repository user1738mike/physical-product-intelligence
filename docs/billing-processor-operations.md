# Billing inbox and reconciliation supervisor

`compose.processors.yaml` includes a separate `billing_processor` using the same
immutable backend image and protected operator connection. It has no public port,
no evidence/backup mount, a read-only root filesystem and a tmpfs heartbeat.
Configure the existing active operator through `PPI_PROCESSOR_ACTOR`.
`PPI_BILLING_PROCESSOR_ENABLED` defaults to false. Enabling it also requires an
available configured adapter; unavailable mode reports zero work honestly.
Production currently has no concrete payment adapter and rejects the simulator.
This service does not make production collection available.

When explicitly enabled, it processes verified inbox records and performs
lookup-only recovery of previously submitted operations. It never calls payment
creation, retries a charge submission, initiates refunds, changes prices or
generates customer statements. Pending operations are untouched until expiry;
expired pending records can be resolved through lookup without submission.
Unknown/ready/abandoned processing records are automatically inspected only until
three days after operation expiry. Older uncertain records remain durable and
require operator review, not guessed failure or a second payment request.

The daemon polls every thirty seconds, selecting at most five operations and five
inbox records by default (maximum ten per lane). Durable `next_check_at` values
give each selected item a sixty-second cooldown shared by replicas. Scheduling
updates finish before provider work; existing services retain authoritative
account locks, verified-event identity, lease fencing, amount/currency checks,
idempotent allocation and access-transition rules. Lookup-observed facts become
eligible for inbox processing in the same cycle. Active ninety-second processing
leases are not taken over. Existing event attempt limits/quarantine are retained.
Financial history is reconciled even when customer access is suspended; ordinary
tenant authorization and explicit paid-access policy remain separate boundaries.

The operator is reloaded before every work item, including maintenance deliveries
and extraction recovery. Disabling it stops subsequent admissions in the same
cycle; already admitted external activity cannot be recalled. Worker DB sessions
use five-second statement, three-second lock and fifteen-second idle-transaction
bounds. Signals set a plain stop flag, avoiding reentrant threading-lock deadlocks.
Sleep polling bounds idle shutdown delay to one second. Services stop after the
current bounded cycle; Compose retains the 240-second grace and health policy.
Host monitoring must check health, failure counts and durable backlogs.

Migration `billing.0003` adds scheduling metadata only. Python and retained
database defaults both use current time so an older compatible application may
omit these fields during rollback. Tests exercise legacy ORM insertion after
upgrade and preserve original operation amounts/fingerprints and verified inbox
hashes/payloads. No financial history, usage or access is fabricated or reset.
The earlier upgrade test now restores actual migration leaves after testing the
pre-billing upgrade, rather than leaving the test DB at a historical schema.

For an explicitly authorized isolated simulator cycle:

```sh
python manage.py run_billing_processor --actor OPERATOR --enabled --once --limit 5
```

This mutates eligible verified records; it is not a dry run. Ordinary startup/CI
does not call a live payment provider. Tests use an isolated PostgreSQL test DB
and the guarded offline simulator, including two actual enabled daemon starts,
settlement without resubmission, clean SIGTERM and no duplicate effect on restart.
Failures retain durable retry state and fixed diagnostics, never provider bodies.

Release backup/rollout/rollback quiesce both processor services. Backups resume
only writers that were running before maintenance, so a newly added service is
not started against an older image/schema. Existing rehearsals upgrading from
the one-worker recipe need the billing worker's same read-only database CA mount
and isolated settings override. Production host usage combines the reviewed
processor recipe with `compose.processors.host.yaml`; provide the approved CA
path and protected configuration on the host, never copy rehearsal secrets.

The database default follows [Django 5.2 db_default](https://docs.djangoproject.com/en/5.2/ref/models/fields/#db-default).
Real provider/country/prices/policies, official adapter implementation and an
authorized sandbox acceptance remain required before paid commercial readiness.
