# Isolated release browser acceptance

This is real Chromium automation, separate from frontend Vitest component tests. It creates new synthetic organizations/records using rendered forms and the real HTTPS ingress, scanner and recorded extraction adapter. Existing fixture users authenticate through the login form. API-only membership management is supporting setup/probing, explicitly distinct from the UI catalog/import/review/rule/assessment journey. No database edits or forced authentication occur. It does not contact an AI provider.

Build and run against the retained isolated rehearsal:

```powershell
docker build -t ppi-phase8b-browser browser-tests
.venv/Scripts/python.exe scripts/browser_acceptance.py --directory artifacts/phase8-final --output artifacts/<new-browser-evidence-directory>
```

The driver refuses non-rehearsal identities, uses a new evidence directory, passes only synthetic fixture context on stdin and mounts only the public CA. Credentials are written mode0600 inside the disposable container; `.env`/OpenAI keys/TLS private keys are never read or mounted. Output passwords are redacted, traces/video/login screenshots are off, and JSON plus an assessment screenshot are retained. No state is deleted from the application.

The browser runs as non-root `pwuser` with `chromiumSandbox: true`. `seccomp_profile.json` is the official version1.64.1 Playwright profile (SHA256 `cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849`), allowing user namespaces so the browser sandbox can operate. Its default action remains `SCMP_ACT_ERRNO`. It is not an unconfined container profile. No privileged/SYS_ADMIN/host IPC or certificate-ignore flags are used; shared memory is separately bounded512MiB.

Only this environment's public CA is added to an NSS database in the isolated container home. Browser certificate validation remains enabled (`ignoreHTTPSErrors: false`); the host/OS trust store is untouched. Base URL is `https://edge:8443` on the rehearsal's Docker network, whose certificate contains the `edge` SAN. This validates private local TLS, not a public deployment certificate. The ordinary in-app browser currently rejects this private CA; do not bypass its warning.

The test guards `synthetic_rehearsal_only` before clicking extraction. It covers secure cookies, organization selection/switching, product/packaging creation, unsupported upload error, clean real-scanned CSV and exact-byte private download, recorded proposal/visible source quote/review/canonical selection, reported dimensions, four explicit dimensional/mass rules, compatible/conflicting/incompatible/missing outcomes, immutable prior snapshot, role/foreign/private-file/revocation denials and logout. A clean process exit plus `acceptance.json` is required for a pass; a prepared test or launched browser alone is not acceptance. Retries are disabled. New synthetic data remains available for review.

For CI, the `browser-acceptance` job builds the actual applications, provisions a fresh isolated HTTPS/real-scanner rehearsal, creates synthetic login context with existing smoke workflows, and executes this runner. Only selected sanitized result files are uploaded, never the rehearsal directory/env/credentials. No live-provider key or production secret is needed. Actual hosted results are a separate gate.

References: [official Playwright Docker and sandbox guidance](https://playwright.dev/docs/docker), [version-pinned seccomp profile](https://github.com/microsoft/playwright/blob/v1.64.1/utils/docker/seccomp_profile.json), and the installed Next.js Playwright testing guide read before implementing this suite.
