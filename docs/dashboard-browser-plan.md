# Dashboard browser verification

The existing sandboxed Chromium runner remains the acceptance entry point. Run it
against a newly generated dashboard rehearsal; historical rehearsals and their
evidence remain unchanged. The fixture credentials travel on stdin and never
enter screenshots, logs or tracked files. TLS verification and Chromium's sandbox
remain enabled. No live AI, payment or deployment action is required.

`browser-tests/tests/release.spec.js` retains the complete catalog, private upload,
recorded extraction, human review, compatibility, commercial, integration,
membership, recovery and retention journey. Its two catalog navigation steps use
the unified sidebar after organization selection. An additional overview step
checks the four real assessment totals and follows the actual recent assessment
and completed-import links back to their detail pages. Integration reveal-once
credentials must clear after organization switching and a role downgrade checked
when the browser regains focus. Restoring administrator access never restores
the transient secret.

`browser-tests/tests/dashboard.spec.js` adds focused coverage:

| Journey                                    | Evidence/check                                                                                                                                                                                              |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Organization chooser and canonical landing | Create two synthetic organizations through customer forms; selecting one opens its dashboard                                                                                                                |
| Persistent workspace                       | Owner and administrator visit all nine sections; URL, current link, organization and single navigation frame agree                                                                                          |
| Product nested routes                      | Create and edit a product, reload the direct detail URL, and use back/forward navigation                                                                                                                    |
| Authoritative summary                      | Compare real overview response with the normal scoped product API and rendered counts, including an archived record                                                                                         |
| Organization request race                  | Hold a real first-organization overview response in the browser, switch to a second organization, release it, and check the second workspace remains visible                                                |
| Error and retry                            | Browser-intercepted core and optional-summary errors expose retry; failed plan/integration regions leave core totals usable; each retry reaches real backend data                                           |
| Responsive and keyboard                    | Desktop, tablet and phone layouts; mobile drawer open, focus containment, Escape dismissal, focus return and link dismissal                                                                                 |
| Authorization                              | Administrator to member role change; member sidebar omits restricted commercial, billing and integration routes; direct routes/API remain denied; foreign organization and revoked membership remain denied |
| Sign out and account access                | Header account link remains reachable; logout removes workspace access; recovery remains reachable                                                                                                          |

Membership setup and denial probes use normal authenticated, CSRF-protected APIs
as supporting fixtures; product creation/editing and navigation use rendered
customer controls. The injected transient failure and held response are browser
fault scenarios, not evidence of a real backend dependency outage. Backend tests
independently establish aggregate correctness, pagination and tenant filtering.

Successful execution requires all Playwright tests and the existing driver's
`acceptance.json`/`execution.json` checks. The dashboard test also writes sanitized
`dashboard-acceptance.json` checkpoints and representative workspace screenshots.
Prepared tests alone do not constitute browser acceptance. Actual runtime identity,
commands and results are recorded in the dashboard walkthrough and completion
checkpoint after execution.

## Executed result: 2026-10-18

The full run in `artifacts/dashboard-browser-r4` passed both Playwright journeys
in 157.232 seconds: 10 dashboard checkpoints and 18 release checkpoints, with no
skipped, failed or flaky tests. The existing driver returned exit zero and wrote
`execution.json`, `acceptance.json` and `dashboard-acceptance.json` with passed
statuses. The synthetic billing processor also passed.

The target was the isolated project `ppi-rehearsal-5f1408662b`, database
`ppi_rehearsal_5f1408662b`, reached through CA-verified
`https://127.0.0.1:24443`. The execution receipt binds backend `5d8336bed8b3`,
final frontend `1d37cff3ff78` and browser runner `28de4a795aa3`; full immutable
identities and source/lockfile hashes are in that receipt. The application inputs
were an uncommitted dashboard increment on baseline `31f5a1970f81`; a subsequent
publication record must bind the reviewed final commit to those application
inputs. Historical release evidence remains separate.

Dashboard observations recorded zero JavaScript runtime errors, zero hydration
errors and zero unexpected HTTP server errors. Three HTTP 503 responses were
explicit browser fault injections. Eleven HTTP authentication/authorization
denials were recorded separately. Both 820-pixel tablet and 390-pixel phone
checks passed drawer focus wrapping, Escape focus return, link dismissal and
absence of horizontal document overflow. The primary product action met the
4.5:1 text-contrast assertion. Desktop and phone screenshots were visually
inspected; the product action is readable and the resolved overview states are
coherent. Eight result text files contained no unredacted Django cookies.

Earlier attempts remain failed evidence: r1 exposed CRLF in the copied Linux
shell runner; r2 exposed Node-side CA trust and an unsynchronized organization
chooser helper; r3 exposed a broad alert selector matching Next.js's route
announcer. Visual review of r3 also found unreadable primary action text. The
runner, synchronization and selectors were corrected; the primary action CSS
was fixed and a browser contrast regression added before the full r4 repeat.
Cookie/header redaction was extended and its JSON-tail cases verified. No TLS
verification was disabled, business assertion removed or earlier failed receipt
rewritten as a pass.

Executed after the isolated HTTPS health/identity preflight and successful
phase2/phase3 smoke seeding with the recorded extraction adapter:

```powershell
.venv/Scripts/python.exe scripts/browser_acceptance.py --directory artifacts/dashboard-rehearsal-r1 --output artifacts/dashboard-browser-r4 --commercial-fixtures --billing-fixtures --integration-fixtures --recovery-fixtures --retention-fixtures
node browser-tests/redaction-check.cjs
.venv/Scripts/python.exe -m unittest discover -s scripts -p 'test_*.py'
```

The redaction regression and all 29 existing script tests passed. Use a new
output directory for any repeat. No live AI call, real payment, remote deployment
or change to an older rehearsal was performed. This dashboard browser pass does
not close the independent image security, hosted CI, deployment or commercial
gates.
