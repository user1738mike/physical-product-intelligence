# Organization overview API

`GET /api/v1/organizations/{organization_id}/dashboard/` returns one read-only
overview for the authenticated user's organization membership. It accepts no
filters or pagination parameters; unknown parameters return 400. The time scope
is explicitly `all_time`. Counts use SQL aggregates over the entire authorized
organization, rather than a list page. Recent lists contain at most five records,
ordered by `created_at DESC, id DESC`.

Owner, admin and member may read the same business summaries, matching existing
product/import/equipment/assessment list permissions. Foreign or revoked
membership and inactive organizations return 404; inactive accounts and anonymous
requests are denied. There is no staff or superuser bypass. Expired or suspended
commercial assignments continue to permit these existing business reads. The
endpoint adds no plan guard to settings, reactivation or commercial history.
Business mutations still use their existing role, entitlement and transactional
services. Responses, including errors, use the existing private no-store policy.

The response contains:

| Field | Meaning |
| --- | --- |
| `generated_at` | UTC response-generation timestamp, not a claim of one atomic database snapshot |
| `scope` | Always `all_time` |
| `organization` | Existing organization serializer: ID, name, slug, active flag, timestamps |
| `role` | Current caller membership role |
| `products` | `total`, `active`, `archived` across all products |
| `imports` | `total`, all eight `by_status` counts, `awaiting_review`, `attention`, `recent` |
| `equipment` | `total`, `draft`, `active`, `archived`, `active_with_activated_rules` |
| `assessments` | `total`, `compatible`, `incompatible`, `indeterminate`, `recent` |

Import attention is exactly awaiting review, failed and completed with errors.
It does not assert that an uploaded or processing job failed. Recent imports
expose only ID, display name, status and creation timestamp. Equipment counted as
`active_with_activated_rules` must be active and have at least one activated rule
set referencing its current numbered specification. Multiple activated versions
count the equipment once; this is configuration availability, not a safety claim.
Recent assessments expose ID, product/equipment IDs, outcome, saved summary and
creation timestamp. Snapshot payloads and private files are not included.

Empty authorized organizations return zero counts and empty recent arrays. A
failed request is unavailable data, never a synthetic zero response. Counts may
change between the six bounded business queries while other users work; refresh
to retrieve a new view. Two ordinary authorization queries plus six business
queries have constant query count, independent of record count. Only status
groups and the two five-row recent lists are materialized in Python.

Commercial, billing and integration summaries are deliberately absent. Optional
owner/admin regions use their existing authorized APIs independently, so forbidden
or unavailable optional data does not prevent the core overview from loading.
Clients must discard previous-organization responses when switching workspace or
losing authentication and must distinguish request errors from empty results.

Regression checks: `python manage.py test organizations.test_dashboard
--settings=config.settings.test` against a confirmed isolated PostgreSQL target.
These verify empty state, more than 25 products, all outcome/status counts,
bounded recent records, current versus stale rule activation, fixed query count,
all roles, tenant/staff/revocation denial and plan lifecycle read compatibility.
