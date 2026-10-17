# Supervised processors

Use `compose.production.yaml` plus `compose.processors.yaml` after controlled
migrations, role grants and explicit provisioning of an active operator username.
Set non-secret `PPI_PROCESSOR_ACTOR` to that operator. Existing staff identities
are not silently elevated. The protected `PPI_MIGRATION_ENV_FILE` supplies the
owner connection required by append-only delivery-attempt and recovery guards;
the HTTP runtime retains its narrower role. Prefer a separately protected file
for this service with only required settings. Do not expose it through HTTP.
Managed PostgreSQL CA trust must be available at its configured path; add an
approved read-only CA mount when using a private CA.

```sh
docker compose -f compose.production.yaml -f compose.processors.yaml config --quiet
docker compose -f compose.production.yaml -f compose.processors.yaml up -d --wait processors
docker compose -f compose.production.yaml -f compose.processors.yaml logs --tail 20 processors
```

The service polls every ten seconds, selects at most twenty due deliveries and
twenty stale extraction jobs per cycle, and deletes at most 500 expired opaque
rate counters. Existing transactional admission, live issuer/tenant/plan checks,
lease fences, attempt/age limits and immutable histories remain authoritative.
No DB transaction surrounds HTTPS I/O. Multiple instances remain subject to
shared global/per-tenant delivery admission; interrupted claims are eligible
after thirty seconds. Stale extraction recovery after ninety seconds fences the
old worker and releases its usage reservation. Recovery leaves a failed retryable
job for explicit human retry; it does not execute the provider again.

No AI processing or payment initiation occurs in this service. AI is additionally
disabled in its environment. Payment inbox/reconciliation lifecycle remains a
separate completion requirement. Ordinary imports are explicit bounded requests,
not an unobserved background queue. Disabled outbound configuration preserves
pending deliveries. Re-enable only with approved hosts, signing roots and egress;
normal expiry/authorization rules are re-evaluated when processing resumes.

The operator is reloaded and checked each cycle. Revoking the operator stops
mutations; provisioning and ongoing owner DB access remain trusted operations.
Output is fixed numeric counts only. Per-item failures do not stop other selected
work; a DB/configuration failure is retried on the next interval without private
exception output. No credentials, source bytes, destinations or provider bodies
are logged. The service mounts no evidence or backup volumes.

SIGTERM/SIGINT stop admission after the current bounded cycle. Compose waits up
to 240 seconds before termination; restart policy is `unless-stopped`. Completed
cycles with no failures touch a non-secret tmpfs heartbeat. Health becomes
unhealthy after 240 seconds without success. Compose does not automatically
restart unhealthy processes: host monitoring must alert on unhealthy state and
nonzero failure counts, and on growing oldest due-delivery/stale-job age. A
container restart automatically resumes durable due work; monitor backlog rather
than treating a running process alone as delivery success.

For one bounded diagnostic cycle use `python manage.py run_processors --once
--actor OPERATOR --limit 20` under the protected owner configuration. This mutates
eligible work and is not a dry run. Existing `dispatch_integrations` and commercial
recovery commands retain their documented operator workflows.

Tests in `operations.test_processors` exercise interrupted claim recovery,
disabled transport, fenced extraction recovery, current-counter preservation,
operator revocation, isolated failure and two real daemon starts/clean SIGTERM
stops against PostgreSQL. External destinations use mocked transport in tests;
the existing isolated client/receiver demonstration remains separate evidence.
