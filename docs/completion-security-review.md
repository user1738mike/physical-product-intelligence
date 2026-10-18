# Completion security review and scan status

Security acceptance remains open. A valid scanner result can fail the vulnerability
policy; it is not equivalent to a transfer failure or a clean security audit.
No High/Critical findings are suppressed, ignored as unfixed or accepted by changing
severity/freshness policy. No production or staging deployment has occurred.

Grype0.120.1, immutable scanner
`sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe`,
used official schema v6.1.10 built2026-10-17T06:27:09Z. Normal host TLS fetched
official metadata/archive; archive SHA-256
`4c2b8b0cd02313f74a50c81c457796660c4997565cc2ff211e09cc1880205c10` verified.
A fresh named-cache offline import and actual DB content checksum bind the receipt
to that archive and scanner. Receipt/cache revalidation enforces48hours, hash,
schema, origin and successful import; a generic manual import is never sufficient.
The historical dirty manifest and previous caches/reports remain unchanged.

Windows bind-mounted archive reads failed with ENOMEM. Docker API transfer to an
isolated native volume resolved cataloging, without a host daemon socket exposed
to the scanner. New scan tooling additionally verifies exported rootfs layers
against the selected immutable Docker reference and the Grype config digest against
exported config bytes. Docker here identifies OCI manifest digests; Grype identifies
their config digest. Both identities and archive SHA-256 are recorded rather than
incorrectly assuming they are the same digest.

The first complete valid scan (`artifacts/completion-native-scans`) reported these
**raw match counts**, which can include multiple packages for the same CVE:

| Image in that receipt | High | Critical | Outcome |
| --- | ---: | ---: | --- |
| billing backend/core | 67 | 0 | failed |
| billing backend with optional SDK | 67 | 0 | failed |
| identity frontend | 74 | 2 | failed |
| PostgreSQL | 100 | 6 | failed |
| ingress | 146 | 28 | failed |
| ClamAV | 0 | 0 | passed (3Medium matches) |
| then-selected identity backend rollback | 67 | 0 | failed |

Full JSON, immutable identities, database provenance and package/CVE/fix review
are retained beside that receipt. These are initial reviewed inputs, not a claim
that later rebuilt artifacts passed. Final affected-image scans include the
explicit compatible backend/frontend rollback pair.

Available remediation has been applied: nginx1.30.6 with distribution updates
using `deploy/ingress.Dockerfile`, supported Node24/PostgreSQL17 Trixie bases,
and removal of unused global npm from the standalone production frontend.
The latter removes the installed vulnerable
brace-expansion/undici package-manager dependency tree; the app starts with node
directly and build/development dependency tooling is retained. Runtime checks,
real browser acceptance passed for these bases; final immutable-image scans
remain required. The Trixie glibc package includes the fix for CVE-2026-5450;
this does not resolve the separate CVE-2026-5435 finding.

Other initial blockers advertise no fixes in their supported distribution.
For example [Debian glibc CVE-2026-5435](https://security-tracker.debian.org/tracker/CVE-2026-5435)
lists stable bookworm/trixie as vulnerable, while the fix is in unstable;
[Debian zlib CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091)
is also unresolved in its packaged releases. Vendor minor/no-DSA classifications
do not override this project's scanner threshold. Installing unstable libc into
the established supported runtime is not a verified production remedy. Final
findings remain open until patched supported artifacts and affected acceptance
checks satisfy the existing policy.

Manual threat review also covers ordinary-session/CSRF and recovery single use,
tenant/membership revocation, role separation, private upload hash/scan checks,
claim grounding, human approval, money idempotency, admission/lease fencing,
outbound DNS/connection checks, and durable file-removal uncertainty. New retention
policies default to preservation; canonical/applied evidence cannot be removed,
and no file deletion is represented as transactionally reversible. Trusted owner
DB tools remain an operator boundary, never a staff shortcut in customer HTTP.
New log fields contain fixed counts/actions, not provider bodies, keys or files.

Production egress, secret provisioning, legal/backup policy and real merchant
adapter acceptance remain target/business decisions, not demonstrated by these
local scans. Automated checks do not constitute a comprehensive security audit.

## Selected candidate and remaining findings

The selected artifacts are core `d268f09eff43`, SDK `31c489cfcd2d`, frontend
`2dcc1b64dbef`, PostgreSQL `2d2b8998d310`, ingress `8078564a9faf`, ClamAV
`638d90201ee7`, compatible backend rollback `0a0d1caa3eae`, and remediated frontend
rollback `eeca9c22bdf3`. The final generated publication record contains full
identities, source/build/lock/evidence hashes and the selected eight-image scan
receipt `artifacts/completion-release-image-scans-r3/summary.json`.

The preceding complete valid scan measured the unchanged selected runtime inputs:

| Selected artifact | High | Critical | Policy |
| --- | ---: | ---: | --- |
| core backend | 67 | 0 | failed |
| SDK backend | 67 | 0 | failed |
| frontend | 54 | 0 | failed |
| PostgreSQL | 85 | 1 | failed |
| ingress | 91 | 17 | failed |
| ClamAV | 0 | 0 | passed; 3 Medium |
| compatible backend rollback | 67 | 0 | failed |

The original frontend rollback `3c8f493bb72f` had 74 High/2 Critical matches,
including three advertised fixes in unused npm. It is superseded by `eeca9c22bdf3`:
all 2181 application files/symlinks are identical to the predecessor; runtime
uses the already patched supported Node image without global npm. Its paired
rollback/forward acceptance passed. The final selected receipt records its
actual scan result; the old artifact's findings are not assigned to the new image.

The trusted database advertises no fixed High/Critical package versions for the
seven unchanged selected artifacts above. Examples include glibc CVE-2026-5435,
zlib CVE-2026-85091 and
[libxml2 CVE-2026-6653](https://security-tracker.debian.org/tracker/CVE-2026-6653).
Debian lists the installed Trixie libxml2 version as vulnerable, with a fix in
unstable. Its minor/no-DSA assessment does not waive the project severity threshold.

There is also a specific database/vendor discrepancy: Grype still marks nginx
`1.30.6-1~trixie` for CVE-2026-15176, CVE-2026-93479 and CVE-2026-97205, while
[nginx's advisory](https://nginx.org/en/security_advisories.html) explicitly lists
1.30.6+ as not vulnerable. This is documented for trusted database correction,
not locally suppressed. Other ingress package findings remain independently.

The smallest next security action is supported package remediation and/or a
trusted upstream database correction, followed by affected exact-image scans
and acceptance. No stale database, ignored unfixed findings, severity overrides,
unstable core library injection, image publication or deployment is used to
manufacture a pass. Security acceptance remains blocked.
