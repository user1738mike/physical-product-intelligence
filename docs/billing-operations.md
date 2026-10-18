# Billing operations and provider boundary

No provider is selected. There is no real adapter, sandbox verification, merchant approval, hosted collection, refund/payout API, live subscription mutation or tax-invoice implementation. The simulator proves only local orchestration. Payment-provider choice, merchant eligibility/account ownership, supported currencies, approved prices/terms, tax/legal requirements, proration, renewal/grace/cancellation/refund/dispute policy and privacy/retention rules must be agreed before a real adapter. Review that provider's current official signature, idempotency, URL and state-retrieval documentation then; generic test proofs must never substitute for it.

Production accepts only disabled collection. `BILLING_PROVIDER=simulator` and `BILLING_SIMULATOR_ENABLED=true` cause configuration failure. The settings check script verifies both boundaries with synthetic configuration. Simulator execution additionally requires explicit test/rehearsal settings and an isolated database identity. Production accounts remain unconfigured; no API key, merchant identity, currency or price is invented or provisioned. Account bindings become immutable once bound; test identities cannot be converted into live identities.

## Migrations/runtime grants

Apply billing migrations with the separate schema owner before rollout. Existing organizations receive unconfigured billing accounts; new enrollment is atomic with organization creation. Nothing is charged or reassigned by backfill. Price/final statement, monetary/allocation/access/correction/audit histories have PostgreSQL append-only protections. Scope/calculation/balance/owner triggers enforce tenant/mode/currency links, paired fulfillment and immutable received evidence. Billing commands require an explicit active staff operator plus migration-owner connection; staff web users retain ordinary membership checks.

Rehearsal bootstrap narrows broad DML grants. For real deployment, provision the same reviewed separation using actual identifiers outside the repo:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA public TO <runtime_role>;
GRANT INSERT ON billing_billingaccount, billing_paymentoperation,
 billing_inbox, billing_billingaudit TO <runtime_role>;
REVOKE INSERT, UPDATE, DELETE ON billing_price, billing_statement,
 billing_moneyevent, billing_allocation, billing_accessgrant,
 billing_statementadjustment, billing_gatewayobject, billing_gatewaycall FROM <runtime_role>;
REVOKE UPDATE, DELETE ON billing_billingaccount, billing_paymentoperation,
 billing_inbox, billing_billingaudit FROM <runtime_role>;
```

Runtime enrollment can only create unconfigured accounts. Privileged processors use the separate owner connection; it must never reach the HTTP application. No runtime TRUNCATE/schema CREATE/owner inheritance is permitted. Verify exact staging grants, restore behavior, backups and immutable constraints before promotion; migrations on a customer/staging database are not implied by local tests.

## Operator commands

All commands use existing protected environment configuration. Do not put secret values or customer documents in reasons. `process` and `reconcile` default to dry run, require an explicit organization and limit 1–100, and need `--apply` for mutations. Never point synthetic commands at customer data.

```sh
python manage.py billing publish-price --actor <operator> --reason '<approval>' --plan <code> --plan-version <version> --code <price-code> --price-version 1 --currency <approved-code> --exponent <approved-exponent> --unit-minor <approved-integer> --mode <test-or-live>
python manage.py billing generate --actor <operator> --reason '<period approval>' --organization <uuid> --price <uuid> --start <UTC-ISO8601> --end <exclusive-UTC-ISO8601> --quantity 1
python manage.py billing revise --actor <operator> --reason '<draft correction>' --organization <uuid> --statement <uuid> --quantity 2 --expected-version 1
python manage.py billing finalize --actor <operator> --reason '<review>' --organization <uuid> --statement <uuid>
python manage.py billing adjust --actor <operator> --reason '<linked correction>' --organization <uuid> --statement <uuid> --operation <unique-correction-uuid> --delta-minor <signed-integer>
python manage.py billing process --actor <operator> --reason '<bounded processing>' --organization <uuid> --limit 20
python manage.py billing process --actor <operator> --reason '<bounded processing>' --organization <uuid> --limit 20 --apply
python manage.py billing reconcile --actor <operator> --reason '<incident review>' --organization <uuid> --limit 20 --apply
```

`generate --replace-access` is an explicit audited decision to replace the current manual assignment after verified full settlement. The default preserves pilot access. There is no automatic usage-to-charge conversion, renewal, immediate failed-payment suspension or proration policy.

Only isolated rehearsal supports `configure-simulator` and `simulate`:

```sh
python manage.py billing configure-simulator --actor <operator> --reason '<synthetic fixture>' --organization <uuid>
python manage.py billing simulate --actor <operator> --reason '<synthetic observation>' --organization <uuid> --operation <uuid> --kind payment.succeeded
# Other synthetic kinds: payment.failed, subscription.cancelled,
# refund.observed (explicit --amount-minor and --reverses effect ID), dispute.observed.
```

Simulation persists a local object state and verified test receipt; processing remains separate. It makes no external request or real payment/refund. The guarded browser fixture command creates only new synthetic accounts/prices/statements and a new operator, without changing existing user privileges. A runner signal after visible pending state invokes the real bounded processor for that fixture organization; the browser then observes settlement and downloads its statement. No database edits replace the billing processing journey.

## Recovery and reconciliation

Durable operations exist before submission. Never hold database locks across an adapter call. A timeout after submission leaves unknown state with the original key. Lookup reconciles an existing object and can recover a missing simulator delivery through authoritative simulator state; it does not create a second charge. A stale worker is fenced before lookup/state changes. Unknown outcomes without an authoritative object remain unresolved, not resubmitted.

Received events survive a worker crash. Claim commits a bounded attempt/lease first, then fetches authoritative state outside transaction, and applies settlement/access atomically with lease verification. Interrupted application rolls back financial/access writes and leaves a retryable inbox. Stale leases can be reclaimed; active workers and late fenced results cannot commit. Unsupported/ambiguous/mismatched events remain ignored/quarantined with fixed diagnostic categories; do not replay all history blindly. Investigate quarantined records against trusted evidence and approved commercial policy. No automatic discrepancy waiver or credit allocation is implemented.

Final statements are immutable. Corrections append actor/reason-linked signed adjustments and cannot reduce the total below existing allocations. Observed refunds link their original receipt and reverse only valid allocated amounts; they do not initiate refunds. Disputes remain review observations, not invented cash movements. Unapplied credit is kept by currency. Reconcile access separately from money: manual pilot and historical evidence remain intact unless an explicit authorized assignment transition occurs.

Keep financial IDs/evidence restricted to operators, avoid logging payloads/signatures/card data, and apply an approved retention/legal-hold policy before customer use. Current normalized event evidence omits profiles/cards/signatures; customer APIs omit merchant/customer IDs and internal operator reasons. Encrypt backups and test restores under the actual target's grants. Hosted exact-candidate CI, fresh valid Grype scans and an approved staging host/domain/region/budget remain release gates; no live collection or deployment is approved here.
