# V1 completion plan and requirement traceability

This is the finite continuation of the Phase 1–10 implementation, starting from
`ed66912080c04a4c44747735c67445511091ea72` on `codex/v1-completion`.
The current master completion attachment (2026-10-17) supersedes phase stopping
instructions. Historical reports remain evidence for their recorded inputs,
not acceptance of subsequent code. No earlier dirty-build manifests are replaced.

Sources: [requirements](product-requirements.md), [roadmap](engineering/phase-roadmap.md),
[domain](domain-model.md), ADRs 0001–0012, original Phase 3–10 user attachments,
and the master completion prompt. `M-A` through `M-J` refer to its capability
sections; `M-7` through `M-10` refer to integrated verification and release.
Phase evidence below links the report with commands and ignored artifact paths.

States distinguish implemented/local functional evidence from unresolved external
and release gates. Final323 backend and15 browser checks cover the completion
inputs within the limits in final-acceptance-report.md; failed image security
findings prevent overall local acceptance. A simulator is never a real adapter.

| ID | Source / required behavior | Implementation | Evidence | State / dependency / next action |
| --- | --- | --- | --- | --- |
| ID-01 | P2, M-A: secure registration/login/logout/session rotation and CSRF | accounts; frontend account; fixed API proxy | phase2-implementation-report; phase10 HTTPS smoke | implemented; final real TLS auth/business/browser acceptance passed |
| ID-02 | P2, M-A: ordinary-account onboarding and organization selection/pagination | accounts, organizations, frontend account | phase10 browser journey | implemented; final suites passed within the documented evidence coverage; final candidate |
| ID-03 | M-A: usable account recovery | accounts RecoveryGrant/services/operator command; account recovery/password forms | 10 final targeted tests; full322-test PostgreSQL increment and14-checkpoint real browser | implemented and locally verified; operator-assisted recovery with single-use/session/key revocation; no verified email assumed |
| ID-04 | P2, M-A/I: owner/admin/member lifecycle, transfer and last owner | organizations services/constraints; settings screen | backend adversarial tests and14-checkpoint real browser | implemented and locally verified; customer membership/ownership/lifecycle forms and authorization |
| ID-05 | P2, M-A: revoked/inactive access across all resources and jobs; no staff tenant bypass | shared authorization + scoped services | backend tenant tests; browser revocation | implemented; processor authority/revocation and customer boundaries verified |
| ID-06 | P2, M-A: audit material actions without secrets | audit; operations logging | backend redaction tests | implemented; final suites passed within the documented evidence coverage; new actions |
| CAT-01 | P3, M-B: tenant-unique immutable SKU; complete numbered revisions; archive | products models/services; product UI | phase3-completion-report | implemented; final suites passed within the documented evidence coverage; |
| CAT-02 | P3, M-B: unit/inner/case/pallet hierarchy, optimistic package history | products workflows/constraints | phase3 tests + browser | implemented; final suites passed within the documented evidence coverage; |
| CAT-03 | P3/P5, M-B: exact units, bounds, nonfinite/invalid rejection | product normalization + compatibility engine | numeric/uncertainty tests | implemented; final suites passed within the documented evidence coverage; |
| CAT-04 | P3, M-B: immutable attributed evidence; declared vs captured hashes | products evidence; ingestion captures | phase3/4 tests | implemented; final suites passed within the documented evidence coverage; captured downloads |
| CAT-05 | P3/P6, M-B: reported/estimated/attested/unknown/conflicting claims and explicit selection | claims, verification and selection services/UI | phase3/6 reports | implemented; final suites passed within the documented evidence coverage; |
| ING-01 | P4, M-C: bounded CSV/XLSX parsing, mapping and row errors | ingestion parsers/worker/services/UI | phase4 report + parser tests | implemented; final suites passed within the documented evidence coverage; |
| ING-02 | P4, M-C: labeled text PDF/TXT, source locations and unsupported-layout errors | isolated ingestion worker | phase4/6 reports | implemented; final suites passed within the documented evidence coverage; |
| ING-03 | P4 conditional OCR, M-C: only promised responsible image/OCR scope | parser explicitly rejects scanned images | original P4 section8: add OCR only if dependencies/execution environment support it responsibly; P3 excludes image recognition; ADR0009 bounded formats | not applicable to agreed formats: no image/OCR dependency or unconditional v1 promise found; CSV/XLSX/text PDF/TXT acceptance remains required |
| ING-04 | P4, M-C: private validation, bounded malware scanning, fail closed | uploads/storage/scanning; ClamAV | phase10 real scanner smoke | implemented; final suites passed within the documented evidence coverage; dependency failure |
| ING-05 | P4/P6, M-C: job states, correction/rejection, cancellation, retries, atomic partial results | ingestion services/ai_services/UI | phase4/6/9A tests | implemented; automatic recovery tracked OPS-02 |
| ING-06 | P4, M-C: human approval and idempotent apply; canonical claims not silently overwritten | candidate/review/apply services | backend race tests + phase10 browser | implemented; final suites passed within the documented evidence coverage; |
| ING-07 | P4/P7, M-C/J: retention/deletion/legal hold without broken provenance | ingestion retention policy, SourceRemoval, DB guards, supervisor, owner UI; retention-aware backup/restore | 11 retention cases within final323;15-checkpoint browser;59-model restore; source-retention.md | implemented and locally verified;11 retention tests, final15-checkpoint browser, post-removal59-model restore; legal/backup production policy remains external |
| EQ-01 | P5, M-D: equipment versions and operational/handling context | compatibility models/services/UI | phase5 report | implemented; final suites passed within the documented evidence coverage; |
| EQ-02 | P5, M-D: immutable typed rules, activation and explicit units/margins | compatibility rules/activation | phase5 engine/DB tests | implemented; final suites passed within the documented evidence coverage; |
| EQ-03 | P5, M-D: deterministic compatible/incompatible/indeterminate, explanations and unknowns | Decimal engine; assessment UI | phase5 boundary tests; phase10 browser | implemented; final suites passed within the documented evidence coverage; |
| EQ-04 | P5, M-D: immutable snapshots/comparison, no safety certification | assessments/comparison UI/exports | snapshot tests + phase10 browser | implemented; final suites passed within the documented evidence coverage; |
| EQ-05 | M-D: agreed batch/measured-feedback/reporting scope, version-linked observations | single assessment, immutable comparison and JSON/CSV exports | P5 immutable history/comparison, ADR0010; domain model explicitly puts physical test methods/artifacts later; P10 bounds per-assessment exports | no additional batch/physical-feedback promise found in Phase1–10 v1 roadmap; comparison/reporting verification remains EQ-04/INT-02; no invented physical outcomes |
| AI-01 | P6, M-E: optional provider, graceful disabled mode | ingestion ai_provider; SDK optional | phase6 tests; check_ai_provider | implemented; zero live calls authorized |
| AI-02 | P6, M-E: strict schema, grounded quote/location, deterministic normalization | ai_schema/ai_services + review | versioned 18-case mock evaluation | implemented; rerun evaluation |
| AI-03 | P6, M-E: leases, global cap, fencing, retries/cancellation, human authority | ingestion + commercial reservations | phase9A/10 backend tests | implemented; supervised recovery locally verified |
| AI-04 | P6, M-E: representative live quality/connectivity evidence separate from mocks | explicit opt-in provider check | not executed | external; specific bounded live-check authorization and fixture consent |
| COM-01 | P9A, M-F: immutable plan versions and effective nonoverlapping assignments | commercial models/services/operator commands | phase9a-completion-report | implemented; final suites passed within the documented evidence coverage; |
| COM-02 | P9A, M-F: centralized entitlement/capacity across normal/import/job paths | common commercial services | quota/admission tests | implemented; final suites passed within the documented evidence coverage; last-unit races |
| COM-03 | P9A, M-F: durable monthly reservations, fencing/idempotent usage and adjustments | reservations/usage/history | PostgreSQL concurrency tests | implemented; final suites passed within the documented evidence coverage; boundaries/recovery |
| COM-04 | P9A, M-F: explicit pilot backfill; historical access; Plan and usage UI | commercial enrollment/API/UI | phase9a browser + upgrade test | implemented; final suites passed within the documented evidence coverage; |
| PAY-01 | P9B, M-G: exact versioned prices, internal statements and arithmetic | billing models/services/UI | phase9b-completion-report | implemented; final suites passed within the documented evidence coverage; |
| PAY-02 | P9B, M-G: durable payment operations and verified event inbox | billing adapter/services | duplicate/out-of-order/unknown tests | implemented provider-independent boundary; concrete adapter PAY-05 |
| PAY-03 | P9B, M-G: strict settlement/access transition and reconciliation | billing ledger/grants/services | PostgreSQL integrity + isolated settlement demo | simulator orchestration verified; production test-mode rejection verified; real provider remains PAY-05 |
| PAY-04 | P9B, M-G: preserve pilot, no fake tax invoice or payment UI | account history and disabled production collection | billing UI/browser tests | implemented; final suites passed within the documented evidence coverage; |
| PAY-05 | P9B, M-G: one real grounded provider adapter and authorized sandbox acceptance | no real adapter | production rejects simulator | external; merchant country/provider/currency/prices/policies and sandbox authorization needed |
| INT-01 | P10, M-H: scoped reveal-once credentials, expiry/revocation/issuer access | integrations services/UI | phase10 26 integration tests | implemented; final suites passed within the documented evidence coverage; |
| INT-02 | P10, M-H: tenant-bound versioned reads, faithful JSON/CSV and admission | integrations views/exports | scope/CSV/rate/concurrency tests | implemented; final suites passed within the documented evidence coverage; |
| INT-03 | P10, M-H: transactional outbox, stable raw signatures, replay/dedupe | integrations events/delivery/signing | actual isolated client/receiver receipt | implemented; supervised dispatch OPS-01 locally verified |
| INT-04 | P10, M-H: bounded SSRF-resistant connection-time egress | transport + production settings | URL/DNS/socket tests | implemented; actual target egress acceptance external |
| INT-05 | P10, M-H: isolated real HTTPS client and signed local receiver | integration_demo; examples | phase10-integration-demo-verified receipt | implemented; rerun affected runtime |
| UI-01 | M-I: usable forms/navigation/errors/progress/role and tenant switch | frontend app workspaces | 59 tests + 11 phase10 browser checkpoints | final15-checkpoint customer browser acceptance passed |
| UI-02 | M-I: no secret persistence, dead customer actions or misleading success | frontend reveal lifecycle; browser redaction | phase10 browser + redaction tests | final customer/browser/secret-boundary checks passed |
| OPS-01 | M-J: supervised automatic webhook dispatcher | operations processors + compose.processors.yaml; release.py lifecycle | PostgreSQL daemon restart/SIGTERM and mid-cycle revocation; healthy actual Compose worker | implemented and locally verified; actual supervised dispatch, quiesce/resume, restart and signed receiver |
| OPS-02 | M-J: automatic stale extraction fencing and quota release without AI execution | same processor using commercial.recover | processor and commercial concurrency tests; healthy actual worker | implemented and locally verified; recovery/fencing/quota release; never invokes AI |
| OPS-03 | P7, M-J: bounded private storage, migrations/runtime role split, health/logs/limits | production/rehearsal recipes; operations | phase7–10 tests and reports | implemented; final suites passed within the documented evidence coverage; new candidate |
| OPS-04 | M-J: necessary billing inbox/reconciliation processor lifecycle | separate bounded lookup-only billing supervisor, disabled by default | 85 billing/operations tests; actual daemon settlement/restart; old writer migration compatibility; healthy disabled Compose service | implemented and locally verified for available isolated adapter; required real provider remains PAY-05 |
| OPS-05 | P7/P8, M-7: backup restore and compatible rollback preserving new enforcement | release.py; recovery commands | earlier phase8 evidence only | locally passed; legacy/new59-model restore, actual HTTPS/private hashes and commercial/scoped integration paired rollback/forward |
| OPS-06 | M-7: bounded measured capacity and dependency failure/restart | existing load/release scripts | earlier receipts only | locally passed; DB/scanner outages, restart and240 reads/4concurrency/0errors/p95 88.89ms; qualify actual target |
| SEC-01 | M-8: focused tenant/file/session/job/money/egress threat review | shared boundaries + regression suites | phase reports/security docs | focused new-path review and final323 backend/15-checkpoint browser passed; no comprehensive security-audit claim |
| SEC-02 | M-8: valid fresh trusted Grype results for app/infrastructure/rollback | official fresh checksum-attested import; native archive transfer; config/layer binding | valid complete eight-image original selection: seven fail severity policy; remediated rollback selection and final exact bindings in generated record | official DB transfer resolved; valid scans fail High/Critical policy; selected8-image results and exact bindings in final generated record |
| REL-01 | M-7/9: all suites, styles/types/schema/migrations/build, zero live CI calls | CI + scripts + eval fixtures | phase10 baseline reports | passed;323 backend,59 frontend,29 tools,18/18 mocked evaluation,15 browser; actual migrations/drift/schema/build checked; zero live calls |
| REL-02 | M-9: focused commits and completion branch publication | verified origin user1738mike/physical-product-intelligence | starting clean Git inventory | reviewed focused completion commits; exact branch/SHA/push/hosted outcomes in generated completion-publication.json |
| REL-03 | M-9: exact-SHA hosted CI, every required job | .github/workflows/ci.yml | prior Phase8B blocked before execution | exact-SHA/all-nine-job hosted inspection result in generated record; no pass inferred from local tests |
| REL-04 | M-9: sanitized exact source/lock/image/evidence manifest outside source | ignored artifacts release manifests | historical manifests preserved | generated sanitized source/lock/build/image/evidence hashes outside Git after final commit |
| REL-05 | M-10: approved staging host/domain/region/budget and real validation | deployment scripts/handoff | no approved target | external; operator packet prepared in completion-deployment.md |
| REL-06 | M-11: authorized production verification and paid commercial readiness | no remote deployment | none claimed | external REL-05/PAY-05/security gates and explicit authorization |

## Completion queue and remaining gates

1. Accepted: supervised dispatch, stale extraction fencing, billing reconciliation,
   account recovery and customer organization/membership lifecycle.
2. Accepted: retention/legal hold, durable file-removal uncertainty, owner UI,
   metadata/provenance preservation and retention-aware recovery.
3. Accepted: final functional backend/frontend/tool/evaluation/browser checks,
   actual current/legacy restore, paired rollback, outages/restart and bounded load.
4. Security gate: trusted eight-image evidence and findings review;
   no severity/freshness relaxation. Supported patches are applied where available.
5. Publication evidence: final documentation/manifest, ordinary completion branch push,
   exact-SHA all-job hosted CI inspection and consolidated external decision packet.
6. External: remaining supported vulnerability fixes, hosted execution eligibility,
   grounded real payment adapter decisions/sandbox, approved staging target and
   deployment authority. Live AI evidence requires its specific authorization.

No speculative roles, robot control, physical safety certification, infrastructure
purchase, image publication or live payment/AI execution is implied.
