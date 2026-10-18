# Original source retention and legal hold

An organization starts with preservation enabled: legal hold active and removal
disabled. An active owner may configure a minimum age (1–36500 days, or disabled),
hold and a non-sensitive change reason in Organization settings. Each change is
an immutable version; optimistic version checks reject lost updates. Members can
read current policy; only owners can change it or request removal. Suspended or
foreign organizations deny access through the normal tenant boundary.

This is unused original-file disposal, not full tenant erasure. Only deterministic
uploads in failed/cancelled state qualify, after the configured age. Every linked
extraction must also be failed/cancelled, with no applied row, evidence or claim.
Canonical product evidence, assessments, source hashes, review metadata, audit,
financial and usage history are preserved. It does not promise GDPR erasure or
infer the business's legal retention period. Approve production retention and
backup schedules independently; no period is guessed or enabled by deployment.
Preview, raw row and proposal values can remain in review records; this removes
the original file bytes, not every content-derived record.

Owners request an eligible file from its import detail, give a reason and confirm
permanent removal. Requests are idempotent while active/completed. The maintenance
processor checks at most its configured cycle limit. It rechecks tenant activity,
current requester ownership, policy version, hold, age, source identity/version,
linked job states and applied provenance under the organization lock. Changed
conditions cancel the request; they never silently resume under a new policy.

A committed claim records intent before touching bytes. New reads/processing and
extraction admission are denied after this claim; PostgreSQL also prevents new
AI jobs and mutation of a removed source's identity. The worker verifies the fixed
tenant/UUID filename, reviewed private filesystem backend, bounded size and actual
SHA-256 before unlinking that one file. It has the private evidence volume; the
billing worker does not. No arbitrary paths or database history are deleted.
After storage verification the worker reacquires the organization lock and checks
the committed claim again. Recovery/reconciliation fences a delayed worker before
unlink; the short filesystem critical section does not make deletion reversible.

Filesystem deletion cannot be rolled back with a DB transaction. Confirmed
completion is recorded separately; storage failure, changed bytes, missing file
or interruption leaves a visible uncertain result. A claim older than five
minutes becomes `needs_review`, without another automatic unlink. A legal hold
cannot be confirmed while claimed/uncertain removal is admitted. It cannot recall
bytes already disclosed or previously removed. A newly enabled hold blocks queued
work; an in-flight action must first finish or be reconciled.

Quiesce maintenance workers and inspect the case before reconciling uncertainty:

```sh
python manage.py reconcile_source_removal --actor OPERATOR --removal UUID \
  --reason CASE_REFERENCE --workers-quiesced
```

The command requires the trusted operator/owner DB connection. It never unlinks.
An intact matching original cancels the request; verified absence records removal.
Changed bytes or unsafe paths remain unresolved. Review records retain reasons,
policy version, checksum and each transition, without logging paths/content.
Resume workers and then apply any hold. Monitor `source_removals_by_state`, alert
immediately on `needs_review` and on queued age/worker health; operator status
also exposes billing inbox/operation and webhook delivery counts without bodies.

Quiesced backups copy retained sources only, preserving confirmed removal metadata
in the protected bundle and full removal history in its DB dump. Uncertain removals
block acceptance. Restore validates original counts and file hashes, confirms the
same removal metadata and rejects resurrection of removed files. Older bundles
remain untouched; the release helper applies controlled forward migrations only
to a new empty isolated restore target after verifying its original records/files.
Historical backups can still contain bytes removed later: their separate approved
retention/access/erasure process is a deployment policy requirement.

Tests use newly created synthetic files and a separate PostgreSQL test database.
The guarded browser fixture creates a new synthetic organization and ages only
its new unused source; it cannot run with production settings. No existing
customer source is selected for acceptance cleanup.
