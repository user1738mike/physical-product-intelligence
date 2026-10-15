# ADR 0012: Small-deployment operational controls

Status: accepted for Phase 7, 2026-10-16. See the [operations guide](../deployment-and-operations.md) and [verification report](../phase7-completion-report.md).

Keep the modular Django/PostgreSQL application and explicit synchronous jobs for the first small deployment. Durable state, source/target revalidation, finite retries and lease-based final persistence already exist. Add a PostgreSQL advisory admission lock and global active-extraction cap, bounded Gunicorn/container policies and explicit interrupted-job recovery. Do not add a queue platform without evidence of throughput or autonomous-recovery requirements. This accepts worker occupation, manual recovery and possible duplicate external billing after uncertain interruption; exactly-once execution is not promised.

Use PostgreSQL atomic fixed-window counters shared across processes, HMAC subject identifiers, authorized user/tenant scopes, peer authentication limits and fail-closed 503 on admission-store failure. This avoids adding Redis solely for throttling. Accept small DB write overhead, fixed-window boundary bursts and the need for consistent secrets/clocks and ingress protection. Preserve bounded paginated read-query budgets by charging write/processing scopes only.

Require explicit migrations before readiness and separate non-owner runtime credentials from migration ownership. Production fails closed on weak config, unverified DB TLS, untrusted proxy ranges, missing private/scanner configuration and elevated/owner runtime DB role. Private storage remains filesystem-based; multi-host object storage is not implied. Add a private ClamAV INSTREAM hook rather than claiming MIME/signature validation is malware protection.

Recovery is operator-driven and data-preserving: quiesced logical DB/private-file bundle, integrity manifest, new empty isolated restore database/root, count/checksum/API verification, no overwrite/automatic deletion/promotion. Restrict and encrypt all bundles; trusted-bundle provenance and production PITR remain deployment responsibilities.

Keep provider validation independent of startup/CI. One explicit opt-in synthetic command uses the existing adapter/schema and bounded request only after separate authorization. Versioned recorded synthetic evaluation measures deterministic validation boundaries; it cannot establish live model quality, source authenticity or semantic attribution. Human review and deterministic compatibility semantics remain unchanged.
