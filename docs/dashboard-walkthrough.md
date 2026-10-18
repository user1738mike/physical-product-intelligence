# Unified organization dashboard

Starting candidate: `31f5a1970f819215bea8b463a44963f597170f5e` on
`codex/v1-completion`. Dashboard work uses `codex/unified-dashboard`.
Existing `.env`, databases, rehearsal images and evidence are preserved.

## Route and navigation map

All `/organizations/[organizationId]/*` routes share a persistent layout.
The organization key resets tenant state when switching organizations. Public,
account and recovery pages keep their existing separate layouts.

| Navigation | Existing or new route | Access policy |
| --- | --- | --- |
| Overview | `/organizations/[organizationId]/dashboard` (new) | Current members; business summary needs active organization |
| Products | `/organizations/[organizationId]/products` | Existing membership, lifecycle and commercial policies |
| Imports and review | `/organizations/[organizationId]/imports` | Existing read/review/application permissions |
| Equipment and rules | `/organizations/[organizationId]/equipment` | Member reads; existing privileged mutations |
| Assessments | `/organizations/[organizationId]/assessments` | Existing member/history and creation policies |
| Plan and usage | `/organizations/[organizationId]/commercial` | Owner/admin only |
| Billing history | `/organizations/[organizationId]/billing` | Owner/admin only |
| Integrations | `/organizations/[organizationId]/integrations` | Owner/admin only |
| Organization settings | `/organizations/[organizationId]/settings` | Member-readable; existing role-specific controls |

Create/edit/detail URLs remain unchanged beneath their sections. Owner/admin-only
navigation is hidden from members, while direct URLs retain server permission
checks and clear denied states. The shell does not require an active paid plan.
Suspended organizations retain appropriate settings/reactivation, commercial,
billing and integration paths according to their existing page policies.

`/products` remains an organization chooser. Account selection and chooser cards
lead to Overview, with explicit links to the catalog available from navigation.
The header provides the organization switcher, account and sign out.

## Using the workspace

Sign in at `/account`. A user with one organization lands on its Overview;
users with multiple memberships choose an organization. `/products` remains a
paginated chooser. An account visit after sign-in continues to expose account,
password and organization-creation controls. Recovery stays at `/account/recover`.

The persistent sidebar marks the active section, including create/edit/detail
routes. The header switches organizations, opens Account and signs out using the
existing CSRF-protected endpoint. On tablet and phone the menu opens a labelled
dialog with contained keyboard focus, Escape/backdrop/close dismissal and return
focus for explicit dismissal. Tables scroll inside the workspace.

Overview shows complete product totals with active/archive labels, import
attention and review counts, equipment lifecycle/current-rule counts, and all-time
assessment outcomes. Recent lists contain at most five actual records and link to
their details. New-work actions retain the existing server entitlement and role
checks. Optional plan/usage and integration delivery regions load independently
for owners/admins. Delivery attention explicitly describes the latest returned
sample (maximum 100), not a global total. Missing data has loading, error and retry
states; it never appears as a zero count.

## API and permission mapping

| Region | Source | Scope and permission |
| --- | --- | --- |
| Header and organization switcher | `/api/v1/auth/me/`, paginated `/api/v1/auth/memberships/` | Caller memberships, including inactive-organization management paths |
| Core totals and recent lists | `/api/v1/organizations/{id}/dashboard/` | Current active-organization member; all-time totals, latest five imports/assessments; eight service queries independent of record count |
| Plan/usage | Existing `/api/v1/organizations/{id}/commercial/` | Owner/admin; separate loading/error/retry |
| Delivery attention | Existing `/api/v1/organizations/{id}/integrations/` | Owner/admin; labelled bounded sample; no credential secrets fetched for overview |
| Customer mutations | Existing section APIs and transactional services | Unchanged CSRF, quotas, history, evidence, signing and credential policies |

See [dashboard API](dashboard-api.md) for the exact response, definitions,
unsupported-filter behavior and permission contract, and
[browser verification](dashboard-browser-plan.md) for the journey/evidence map.

The shell revalidates membership on route changes, focus, visible-tab return and
settings mutations. Stale access responses are ignored. Organization changes
hide the previous content immediately and mount a new keyed workspace; user,
role and activity changes remount the section so ephemeral credential reveals
cannot carry over. No customer session or credential is placed in browser storage.
Server authorization remains authoritative for every request. There is no blanket
active-plan guard: expired-plan history and the existing inactive management paths
continue to use their established page/API permissions.

## Verification checkpoint

Commands are from the repository root unless noted. Evidence is ignored and local;
synthetic credentials/env files are never published.

| Check | Actual result |
| --- | --- |
| Frontend, from `frontend`: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | PASSED: 73 tests in 13 files; all style/type/build commands exited 0 |
| Backend `ruff check` and `ruff format --check`, `backend scripts`, explicit backend config | PASSED; integrations import classification is now consistent across working directories |
| `python -m unittest discover -s scripts -p 'test_*.py'` | PASSED: 29 tests |
| Backend system, migration drift and strict OpenAPI checks | PASSED offline and against the final PostgreSQL rehearsal using its runtime role; `artifacts/dashboard-backend-checks.log`, schema retest and `dashboard-runtime-checks.log` |
| Full PostgreSQL backend suite | PASSED: 331 tests, 480.286s, exit 0; final dashboard 8/8 repeat passed in 1.866s; both unique test database pairs confirmed absent after teardown |
| Real HTTPS browser journeys | PASSED: 2/2 Playwright tests, 28 checkpoints (10 dashboard +18 full business), 157.232s, zero skips/flaky/unexpected outcomes; `artifacts/dashboard-browser-r4` |

Production backend/frontend and sandboxed Chromium images were built locally.
The fresh rehearsal uses project `ppi-rehearsal-5f1408662b`, a new database/private
root and `https://127.0.0.1:24443`; protected state and immutable image IDs are in
`artifacts/dashboard-rehearsal-r1/release.json`. Historical rehearsals and the
development app remain intact. An initial preparation failed because the child
process could not locate Windows PowerShell for read-only route inventory; only
the preparation process PATH was extended, and a fresh directory was used.

Initial account-render tests needed an App Router mock after adding navigation;
the final suite passes with its original loading/security assertions. Strict
OpenAPI validation exposed an empty query-schema annotation; removing the empty
annotation preserved runtime rejection of unsupported parameters and passed schema
revalidation. Failed attempts remain distinguishable from final passes.

Final browser execution used real sandboxed Chromium 156.0.8078.4 and verified
TLS with this target's public CA. Owner/admin visited all nine sections; member,
foreign and revoked paths remained denied. Dashboard observations recorded zero
runtime/hydration errors and zero unexpected server errors. Three explicit
browser-injected 503 responses exercised independent retry, and eleven expected
authentication/authorization denials were recorded separately. These injected
faults do not claim a real infrastructure outage. Tablet (820px) and phone (390px) navigation,
focus containment/dismissal, overflow and primary-button contrast were checked.
Desktop and phone PNGs were visually inspected.

The final repeat fixed one observed application defect: the shared link color
overrode primary button text, producing green text on green. The scoped primary
link rule restores white text; actual browser contrast regressions pass at both
820px and390px. Optional refresh controls now have their own line and spacing.
Earlier r1–r3 outcomes remain retained as failed overall runs: CRLF launcher,
Playwright request-client CA trust, chooser-loading/route-announcer test selectors,
and the visible button defect were corrected. Browser log redaction now covers
session/CSRF cookies and sensitive headers, including JSON-ending regression cases;
failed receipts retain their status and diagnostics with secrets removed.

Reproduce the existing guarded browser entry point with a NEW evidence directory:

```powershell
.\.venv\Scripts\python.exe scripts/browser_acceptance.py --directory artifacts/dashboard-rehearsal-r1 --output artifacts/dashboard-browser-next --commercial-fixtures --billing-fixtures --integration-fixtures --recovery-fixtures --retention-fixtures
```

It validates the synthetic project/database before fixtures, runs the actual
frontend/backend/proxy/scanner and records the exact immutable identities. The
final selected backend is `sha256:5d8336bed8b3ec07c54a4722eae76c0ac56f40f24c7f0911513e2e629db9da6a`;
frontend is `sha256:1d37cff3ff78cf7e453d6d32293c6f1d5c8c2b33a5a26796817c5687285e99eb`.
The final CSS change was rebuilt and received the full frontend checks and browser
repeat; backend functionality remained unchanged after its 331 + 8 tests. A comparison of 187 backend
source/configuration files match the deployed immutable core image byte-for-byte
(`artifacts/dashboard-backend-image-binding.json`). The full backend tests used
the unchanged locked SDK dependency image with current backend source mounted
read-only and uniquely absent test databases, under a 2 CPU / 1 GiB cap. Their original
target and input hashes are in `artifacts/dashboard-backend-verification.json`.

Publication identity, source/build/evidence fingerprints and the exact-SHA hosted
result are recorded after the final commit in ignored
`artifacts/dashboard-publication.json`. Report-only updates are separate from the
tested application inputs; no self-referencing SHA edit/retest loop is required.
The normal workflow was inspected: nine jobs run local checks/builds/scans and
synthetic browser tests; it performs no image publication, live AI/payment or
remote deployment. Passing local dashboard verification cannot establish a hosted
pass or clear the pre-existing image policy/provider/deployment gates. The new
dashboard application images have not received a passing release vulnerability
verdict in this increment.

This increment does not clear existing image security, hosted CI, payment-provider
or deployment gates. No live AI/payment request, image publication, remote
deployment, environment rotation or historical database/volume removal occurs.
