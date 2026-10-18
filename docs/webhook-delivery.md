# Customer webhook delivery and operations

Customer outbound notifications are separate from the billing inbox, payment-provider identities and payment signature rules. No real customer destination is enabled by this implementation task.

## Transactional event contract

`assessment.completed` is created inside the successful deterministic assessment transaction, together with its existing usage unit. Transaction rollback removes both event and queued deliveries. Retrying an idempotent assessment returns the same assessment and produces no second event or usage. No old assessment/event is fabricated by migration.

An immutable schema-1 compact JSON body contains `schema_version`, stable UUID `id`, `type`, original `occurred_at`, `organization_id`, and thin `data:{assessment_id,overall,path}`. `path` is the relative authorized integration detail API, not a public document URL. Event ownership must match the immutable assessment. Each subscribed enabled destination receives one unique event/destination delivery binding, pinned to its revision. Retries/replay reuse identical raw bytes and event ID.

Delivery is **at least once**. A timeout may follow successful consumer receipt. Consumers must verify signatures before parsing and deduplicate persistent event IDs, committing their own effects and deduplication atomically. The example receiver also rejects conflicting body hashes under a previously accepted ID. External exactly-once effects are not promised.

## Standard Webhooks signing

The implementation follows the current [Standard Webhooks specification](https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md), version 1.0.0, checked 17 October 2026. Headers are `webhook-id`, integer Unix-seconds `webhook-timestamp`, and `webhook-signature`. HMAC-SHA256 signs `id.timestamp.raw_body`; signatures are `v1,<base64>` and multiple signatures are space separated. Revealed endpoint secrets use `whsec_<base64>`. Each attempt has its own timestamp; original event time/ID/body remain fixed. The reference verifier uses constant-time comparison and a five-minute clock tolerance. Keep clocks synchronized and deduplicate beyond the signature time window according to receiver retention needs.

Endpoint signing material is derived with HMAC-SHA256 from a dedicated, versioned server-side root and context `ppi-webhooks-v1:<endpoint-uuid>:<endpoint-key-version>`. Roots are distinct from Django, API bearer and payment secrets, are not stored in database rows, and must come from secure environment configuration. Endpoint rows retain root/key version identifiers only. This is retrievable versioned derivation, not an unusable hash-only outbound secret. Initial creation and explicit rotation reveal a derived endpoint secret once. General metadata never reveals it.

Ordinary endpoint rotation sends current and previous signatures for at most 24 hours; a second rotation drops older generations. Immediate compromised-key replacement emits only the new generation. Retain required root versions until their endpoints are replaced; changing a root under an existing version invalidates derived keys and is prohibited operationally. Root retirement requires explicit endpoint migration/recreation, receiver coordination and pending-work review. Protect root access and encrypted backups separately. A new root must not be copied into repository files, logs or UI.

## Destination security

The HTTP transport implements an operator-controlled exact hostname allowlist, HTTPS/443 only, canonical ASCII host parsing, no userinfo/fragments/percent escapes/control characters/backslashes, default certificate/hostname verification, and no redirects. Every attempt resolves DNS again, rejects the entire answer set if any IPv4/IPv6 address is non-public/reserved, and connects a socket directly to one validated address. TLS retains the original hostname for SNI/certificate checks. There is no unchecked second DNS resolution or environment-proxy routing. See [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).

At most two DNS lookups can be outstanding; admission fails when occupied rather than queueing unbounded work. DNS waits at most two seconds. Connect/TLS use bounded socket timeouts; a ten-second socket shutdown deadline bounds request/response handling after connection. Response bodies are limited to 4096 bytes and discarded. Header parsing uses standard-library bounds. No response bodies, signatures or customer payloads are retained in diagnostics. A redirect is a failure, never a new destination. Required production defense in depth: isolated dispatcher network identity, deny private/metadata/internal egress, approved DNS, outbound firewall/proxy policy, root-secret isolation and target-specific TLS tests. Application checks do not replace network egress controls.

Production defaults to disabled outbound delivery. Enable only after operator approval with `INTEGRATION_OUTBOUND_ENABLED=true`, exact `INTEGRATION_ALLOWED_HOSTS`, `INTEGRATION_SIGNING_CURRENT`, and a secure JSON `INTEGRATION_SIGNING_KEYS` version map containing dedicated base64 roots of 32–64 random bytes. At most three retained root versions are accepted. Production refuses test transports, missing/invalid enabled signing configuration and known synthetic roots. No actual values were provisioned here.

Rehearsal settings have a public synthetic root, `warehouse.example` allowlist and explicit test-transport flag only after the existing disposable database identity guard passes. Normal `transport.send` still rejects private addresses. The demo's loopback sender is separate and rechecks both rehearsal settings and database identity; it cannot be selected through production configuration, customer APIs or the normal dispatcher command.

## Dispatch, revision and recovery policy

States: `pending`, `claimed`, `delivered`, `retryable`, `terminal`, `paused`. Claims commit a random lease before I/O. Leases last 30 seconds and stale claims can be reclaimed. Global PostgreSQL admission caps four active deliveries, with at most two per organization. Lock ordering is organization before delivery; a bounded global claim lock serializes admission. No business transaction is held during DNS/HTTP I/O. Completion rechecks the lease, destination revision, issuer role, organization and current webhook entitlement; stale results are fenced.

Every dispatch rechecks active organization, active owner/admin issuer, current entitlement, destination state/revision and subscriptions pinned by enqueue. A destination edit/disable advances its revision and pauses queued/claimed old work; it is never silently redirected to a new URL. Such work cannot be replayed to a different revision. Already admitted network requests cannot be recalled; disablement prevents subsequent dispatch and fences completion. Coordinate receiver retirement accordingly.

Only 2xx marks success. HTTP 410 disables the endpoint and pauses remaining work. HTTP 429 and other failures schedule retries without sleeping. Backoff is 30, 60, 120, 240, 480 seconds plus 0–15 seconds random jitter; attempts stop at six or three-day expiry. Numeric and HTTP-date `Retry-After` values are respected within a 1–3600 second bound; invalid values use the normal schedule. Redirects are recorded as rejected. Timeouts are ambiguous and retry under the same event ID. Paused work needs operator/customer review, not blind replay. Manual replay is explicit, audited, same event/body/destination revision, at most three times, with a renewed bounded retry window and no new business usage.

Run a bounded batch through the protected database-owner connection, never the HTTP runtime role:

```sh
python manage.py dispatch_integrations --organization <uuid> --actor <operator> --limit 20
python manage.py dispatch_integrations --organization <uuid> --actor <operator> --limit 20 --apply
python manage.py publish_integration_plan --actor <operator> --base-plan <uuid> --plan-version <higher-version> --credentials-limit 3 --destinations-limit 2 --reason '<reviewed approval>'
```

Dry run is default and performs no dispatch. Limit is 1–100. Plan assignment remains a separate explicit Phase 9A operation. The implementation adds no scheduler/queue platform; configure an approved bounded worker cadence only on the eventual authorized target. Monitor due/terminal/paused counts, lease age and sanitized categories; review incidents without dumping payloads or secrets.

## Database, migration, retention and demonstration

Migrations create integration tables/guards only; existing plans, assignments, products, assessments and billing history remain intact. Append-only event/policy/attempt triggers, tenant links, immutable credential verifiers/scopes, final revocation, delivery identity and bounded state checks backstop services. Policy insertion requires the owner connection and a new unassigned plan version. Runtime cannot fabricate processing success or rewrite immutable histories. New rehearsal grants revoke inappropriate update/delete and policy/attempt insertion; verify equivalent target grants explicitly before deployment. Do not grant runtime TRUNCATE, DDL, owner inheritance or dispatcher credentials.

After the target's reviewed base grants, apply the equivalent narrowing under its protected owner connection (replace `<runtime_role>` with the verified identifier):

```sql
REVOKE UPDATE, DELETE ON integrations_event, integrations_planpolicy,
 integrations_deliveryattempt FROM <runtime_role>;
REVOKE INSERT ON integrations_planpolicy, integrations_deliveryattempt FROM <runtime_role>;
REVOKE DELETE ON integrations_credential, integrations_destination,
 integrations_delivery FROM <runtime_role>;
```

Runtime retains permitted enrollment/management/enqueue/replay and transient admission operations; PostgreSQL triggers separately reject processing-state fabrication. Replay locks only its delivery row, so it does not require update rights on joined immutable event rows. Test these exact privileges rather than broadening them to make an operator request work.

Use encrypted backups and a reviewed retention/legal-hold policy for event and financial history. This phase intentionally provides no purge shortcut around append-only protections. Credential verifiers and revoked identities remain auditable; last-use is coarsened to at most one update per minute, without IP/user-agent history. Pending body metadata is thin but tenant-private. Broad customer payload/signature logging remains prohibited. Target-specific upgrade/restore and egress/firewall acceptance remain release gates.

Offline reference examples:

```sh
python examples/warehouse_receiver.py
python examples/warehouse_client.py
```

The receiver default tests synthetic signature verification/deduplication in memory; the client default makes no request. Explicit receiver `--serve` binds loopback and requires its secret through secure configuration. Its optional SQLite path is a demonstration, not a multi-host production deduplication service. The client uses explicit HTTPS origin/header authentication, a bounded read and no redirects.

For a newly prepared synthetic rehearsal only:

```sh
python scripts/integration_demo.py --directory artifacts/phase10-rehearsal --output artifacts/phase10-integration-demo
python scripts/browser_acceptance.py --directory artifacts/phase10-rehearsal --output artifacts/phase10-browser-final --commercial-fixtures --billing-fixtures --integration-fixtures
```

The integration demo creates new synthetic users/organization/plan, uses actual private-CA HTTPS session and bearer APIs, commits an indeterminate assessment, sends signed bytes over a loopback TCP receiver, replays/deduplicates, fetches its export, revokes the credential and requires the next read to return 401. It persists only a sanitized receipt. It does not call a customer destination or weaken the normal SSRF transport. See the completion report for what actually executed and its exact artifacts.
