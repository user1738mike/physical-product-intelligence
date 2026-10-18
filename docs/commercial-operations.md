# Commercial operations

Mutations require a separate migration-owner connection and explicit active staff operator account. They are trusted commands, not staff web shortcuts. Assignments/transitions retain actor/reason, operator reviews have append-only records, and corrections link their original event. Never include secrets or private document content in reasons.

Published `(code,version)` plans are immutable in ORM and PostgreSQL. Changes create new versions. PostgreSQL GiST exclusion constraints (`btree_gist`, installed by migration owner) prevent overlapping assignments under concurrent SQL. Assignment identity cannot change; suspend/resume or shortening the end records a transition. Replacement closes current access and creates a new assignment atomically. Conflicting future assignments are rejected rather than silently rewritten. Resume cannot extend an expired period. Reads determine expiry without scheduler execution.

## Migration and grants

Apply commercial migrations through the controlled release migration owner before rolling out the application. Backfill enrolls existing organizations in unlimited manual pilot without changing business history; it is idempotent and preserves deliberate assignments. New organization enrollment is atomic. Account metering start is explicit; historical usage is incomplete and no old counts are fabricated. Missing policy fails closed.

Runtime stays a non-owner/non-superuser without owner membership or schema CREATE. Narrow existing table DML grants as follows, substituting reviewed identifiers through the established host provisioning process:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA public TO <runtime_role>;
GRANT INSERT ON commercial_plan, commercial_account, commercial_assignment,
 commercial_assignmentevent, commercial_reservation, commercial_reservationevent,
 commercial_usage TO <runtime_role>;
GRANT UPDATE ON commercial_reservation TO <runtime_role>;
REVOKE UPDATE, DELETE ON commercial_plan, commercial_account, commercial_assignment,
 commercial_assignmentevent, commercial_reservationevent, commercial_usage,
 commercial_operatorevent FROM <runtime_role>;
REVOKE INSERT ON commercial_operatorevent FROM <runtime_role>;
```

Database triggers restrict runtime plan insertion to canonical pilot version 1 and assignment insertion to initial enrollment only. Append-only/scope/finalization guards remain effective even with broad DML grants. Never grant TRUNCATE, trigger disabling or migration ownership. Rehearsal bootstrap applies narrowed grants. Review default privileges deliberately for later tables and verify the exact staging role after migrations. Owner credentials remain a trusted external boundary.

## Operator commands

Use protected environment configuration and deliberately select the database. These examples do not authorize a remote change. A reviewed non-secret policy file contains exactly the eight documented keys, without prices or paid status.

```sh
python manage.py commercial publish --actor <operator> --reason '<review>' --plan <code> --plan-version 1 --name '<name>' --policy-file <policy.json>
python manage.py commercial assign --actor <operator> --reason '<pilot access>' --organization <uuid> --plan <code> --plan-version 1
python manage.py commercial assign --actor <operator> --reason '<scheduled replacement>' --organization <uuid> --plan <code> --plan-version 2 --starts-at <UTC-ISO8601> --ends-at <exclusive-UTC-ISO8601>
python manage.py commercial suspend --actor <operator> --reason '<reason>' --organization <uuid> --assignment <uuid>
python manage.py commercial resume --actor <operator> --reason '<reason>' --organization <uuid> --assignment <uuid>
python manage.py commercial expire --actor <operator> --reason '<reason>' --organization <uuid> --assignment <uuid> --ends-at <exclusive-UTC-ISO8601>
python manage.py commercial recover --actor <operator> --reason '<incident>' --organization <uuid> --limit 50
python manage.py commercial reconcile --actor <operator> --reason '<review>' --organization <uuid>
python manage.py commercial adjust --actor <operator> --reason '<correction>' --organization <uuid> --usage <original-uuid> --amount -1 --operation <unique-correction-uuid>
```

Corrections append signed adjustments; originals are never changed. Idempotent correction retries must repeat original event, amount, reason, organization/meter and operation identity. Changed input conflicts, and resulting usage cannot be negative. No money is charged.

## Reservations and reconciliation

Organization row locks serialize admission/capacity. Monthly admission checks finalized signed usage plus durable reservations. Tenant/meter/operation uniqueness and digests prevent duplicates/input reuse. Usage and finalization commit with the business operation; deferred constraints require the pair. Immutable ledger/decision events preserve the plan and pinned month.

AI uses the existing 90-second lease/attempt fencing. Provider work holds no transaction. Failure releases its reservation. Cancellation and stale recovery change the locked job state/lease before releasing; a late worker cannot finalize. Reservations never expire independently of the worker. Deterministic processing and assessments use single transactions, so crashes roll back. Recovery handles only 1–100 stale AI jobs per command and preserves evidence. A released retry uses its original month and current access policy.

Reconciliation audits the review, reports missing assessment events since metering start, finalized reservations missing ledger events, and outstanding reservations. It never manufactures history or silently changes totals. Investigate authoritative business outcomes before explicit linked corrections. Retain original records, backups and audit evidence.

## Payment integration prerequisites

Approve provider/merchant owner, pricing/currency/tax policy, customer/legal terms, cancellation/refund/grace policy, webhook verification/idempotency and sandbox testing. Specify how verified payment events drive these versioned assignments. Live requests and secret provisioning require separate authorization. Exact-candidate hosted CI, fresh image scans and approved staging validation remain release prerequisites. Checkout, recurring collection, tax invoices, overages and provider integration are absent.
