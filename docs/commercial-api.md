# Commercial access API

Phase 9A provides manual access and usage accounting, with no payments, prices or renewal commitments.

`GET /api/v1/organizations/{organization_id}/commercial/` uses existing sessions and private/no-store responses. Owners/admins can inspect it, including when commercial/organization access is suspended. Members receive 403; foreign tenants and revoked memberships receive 404. Staff does not bypass membership. No customer plan, assignment, quota or usage mutation endpoint exists.

Response: `status` (active/suspended/expired/unassigned), `plan` (code/version/name/features), exclusive access dates, UTC `period_start/period_end`, `metering_started_at`, `historical_usage_complete: false`, three `meters`, and the latest 50 assignments. Meters contain definition, limit, used, reserved and remaining. Null means explicitly unlimited; zero means no allowance. A false feature is unavailable regardless of its quota. History omits operator identities/internal reasons.

Policy accepts exactly five boolean keys: `catalog_write`, `evidence_import`, `equipment_write`, `assessments`, `ai_extraction`; and three nonnegative integer-or-null keys: `active_products_limit`, `assessments_limit`, `extractions_limit`. Unknown keys, boolean-as-integer and implicit unlimited strings are rejected. Manual pilot version 1 preserves existing functionality with all features included and unlimited quotas. AI inclusion never overrides configuration, provider availability or human review.

| Operation | Existing role | Additional policy |
| --- | --- | --- |
| Create/reactivate products | Contributors for creation; owner/admin for state | Catalog enabled; active capacity available |
| Edit catalog/packaging/claims | Existing contributor/reviewer | Catalog enabled |
| Upload/validate/map/process imports | Existing contributor | Imports enabled; generation needs extraction allowance |
| Queue/process AI extraction | Owner/admin | AI/imports enabled; configured provider; extraction allowance |
| Review/apply | Owner/admin | Catalog enabled; imported creation also checks capacity |
| Equipment/rules/activation | Owner/admin | Equipment editing enabled |
| New assessment | Contributor | Assessments enabled; monthly allowance |
| Historical records/private files | Existing scoped member | No quota requirement |
| Archive/cancel | Existing state/reviewer role | Cleanup remains available |
| Inspect commercial data | Owner/admin | No active plan required |

**Active products:** current capacity, not monthly events. Archival releases it; reactivation competes again. Downgrades retain existing records and permit cleanup. Bulk apply is atomic: exceeding capacity rolls back all changes in that apply; already completed extraction usage remains valid.

**Assessments:** one unit per committed result, including indeterminate. Existing request UUID/digest makes retries idempotent and rejects changed operands. Admission, result and ledger commit together; failures consume nothing.

**Extraction jobs:** one unit per successfully completed candidate-generation operation, deterministic or AI, independent of candidate count. This boundary is commonly `awaiting_review`, separate from later human review/application. Empty or unusable output still completes bounded extraction; provider/parser failure does not. Later cancellation/review does not erase or add completed usage. Cancelling an in-progress reservation releases it.

Windows are UTC calendar months `[start,end)`. First processing admission pins an extraction's month, including retries/completion after month-end. Plan replacement never resets shared totals. Each admission preserves the assignment/version; released retries compete again under current policy. Already reserved work may complete after access changes while source, membership and worker fencing remain mandatory.

Stable DRF error codes: `access_expired`, `access_suspended`, `feature_unavailable`, `capacity_exhausted`, `quota_exhausted`, `operation_conflict`, `reservation_fenced`, `policy_unavailable`, `policy_inconsistent`. Policy denials are 403, distinct from operational 429 throttles, ordinary permission denial and dependency unavailability. Quota errors explain limits, counts and exclusive reset date. The frontend retains the code and presents the explanation.

Plan and usage uses uncached tenant-keyed reads, clears old data during refresh/switching, rejects stale responses and refreshes on focus or request. Every read rechecks server membership. The screen supports unlimited, exhausted, suspended, expired, unassigned/loading/error states without a nonfunctional checkout action. OpenAPI describes the read-only response.
