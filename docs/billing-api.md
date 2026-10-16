# Internal billing workflows

Phase 9B implements provider-independent persistence and an executable **offline simulator**, not a real gateway integration. No merchant, price, currency, tax treatment or commercial term is selected for customers. Production collection is unavailable and the UI has no Pay/checkout button. Internal statements are not tax invoices. Allowance usage is never converted into charges.

## Permission/API contract

All organization routes use existing session/CSRF and private/no-store conventions. Owner/admin is required; members get 403, foreign/revoked memberships 404. Staff does not bypass web membership. Historical commercial/billing reads remain available to owner/admin during suspended/expired access. The customer cannot configure prices, alter statements/meters, assign plans, mark payment success or select an external customer/merchant.

| Method/path under `/api/v1/organizations/{org}/billing/` | Behavior |
| --- | --- |
| `GET /` | Latest 50 statements/operations, settlement/status and unapplied credit by currency; collection availability |
| `GET statements/{id}/` | Scoped frozen statement, signed corrections and allocation/refund history |
| `GET statements/{id}/download/` | Authorized private plain-text internal statement; no external identifiers or operator notes |
| `POST operations/` | Owner/admin request `{statement_id, request_id}`; currently available only to isolated simulator configurations |
| `GET operations/{id}/` | Scoped durable operation status, bound amount/currency and confirmation expiry |

Unknown fields, including amount, price/customer/merchant IDs or return URLs, are rejected. The server resolves the statement, price version, balance, currency, principal, mode and period. Request UUID is unique per billing account; changed principal/statement/input conflicts. Repeating the same request returns the original operation. Another identity cannot start a second operation while pending/processing/unknown/ready work is unresolved. No browser query, redirect or client status creates settlement/access.

Money is integer minor units and transported as strings. Statement currency/exponent are explicit; UI uses BigInt arithmetic. The deliberately narrow supported exponent metadata is USD/EUR/KES=2, JPY=0, KWD=3, verified against [SIX ISO 4217 List One](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml) on 2026-10-16. This is capability metadata, not customer currency selection or gateway eligibility. ISO lists XTS minor unit as N.A.; simulator fixtures explicitly use XTS with exponent zero. XTS is rejected for live prices. Provider-specific amount conventions must be reviewed when a real adapter is selected.

## State and financial rules

Prices are immutable `(code,version)` records tied to immutable Phase 9A plan versions. Price amount is bounded at 10^12 minor units, quantity 1–1,000,000, and statement total at 10^15. Only exact integers are accepted, not floats or boolean integers. One account/mode/period has one statement; conflicting generation is rejected. Draft quantity revisions require an expected version. Finalization snapshots plan/price versions, currency/exponent, quantity, dates and fixed-price calculation basis. Finalized records cannot change; linked signed adjustments retain actor/reason and operation identity. Corrections cannot erase allocations or create negative/out-of-bound balances.

Statement settlement is derived: draft, pending, partially_settled, settled; discrepancies/refund/dispute review add action_required. The snapshot and original amount remain visible alongside the effective total and corrections. Allocation and refund records are append-only, currency/tenant/period bound, and cannot exceed receipt/statement balances. Unapplied money remains credit, never silently allocated or used for access. Explicit operator installments can demonstrate partial settlement; the public API cannot pick an installment amount.

Operations progress pending → processing → ready or unknown; verified events may produce succeeded/failed/cancelled, and safe unsubmitted requests can expire. Unknown submission is not a failure permitting a new charge. Processing uses a 90-second lease and stable operation/provider idempotency identity. Durable submission precedes adapter invocation, with no service transaction spanning that call. Recovery fences stale workers and performs lookup only, never blind submission. Active workers are not reclaimed.

## Verified inbox and fulfillment

`POST /api/v1/billing/synthetic-inbox/` is **test-only ingress**, with its own public synthetic HMAC proof (`X-PPI-Test-Time` and `X-PPI-Test-Proof`) over timestamp plus untouched body, five-minute replay window and 64 KiB limit. It is not Stripe/Paddle verification and cannot be enabled as a live payment source. Production settings reject simulator/provider enablement. Runtime additionally requires an explicit isolated rehearsal database/settings or Django's isolated test database. No real signing secret or payment credential is used.

Accepted events are stored before 202; storage failure yields retryable 503. Receipt does not settle anything. Merchant/mode/customer map only to server-owned account bindings, then object identity resolves within that account. Submitted organization metadata is not accepted. Identity is provider/merchant/mode/event ID, with canonical semantic hash; equivalent deliveries are idempotent and conflicting reuse is rejected. Retained payloads contain only bounded IDs, amounts, currency, period, kind and object version; no card/customer profile or signature is stored.

Inbox states are received, processing, retry, applied, ignored, quarantined. Fenced processing attempts are durable and bounded at five. Authoritative simulator object versions/current state are checked outside the financial transaction; ambiguous/out-of-order events are quarantined. Valid unsupported events can be ignored. Equivalent business effects use account/effect identity independently of event identity.

Settlement, allocation and an authorized Phase 9A assignment link commit atomically. Amount/currency/price/period/mode/object/account must agree. Under/overpayment or late confirmation remains observed, unapplied credit requiring review. A late completed financial settlement cannot silently grant expired access. Full settlement grants only when an operator explicitly authorized replacement on that statement; otherwise manual pilot remains. Future access starts no earlier than its statement period. No assignment resets quota history. Failed payment never invents immediate suspension. Cancellation does not renew/extend access; existing access ends as previously assigned. Observed refunds reverse only known receipts/allocations; disputes do not invent a refund. Both require access-policy review without automatic suspension or refund initiation.

Billing history supports delayed confirmation, manual/focus refresh, tenant-keyed requests and stale-response rejection. It displays ordinary availability/status text, exact amounts and private downloads, with no fake-provider labels, developer setup instructions or nonfunctional payment action.
