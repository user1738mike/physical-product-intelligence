# ADR 0011: Optional AI extraction into existing review candidates

Status: accepted for Phase 6, 2026-10-15.

Unstructured product documents need interpretation without granting models authority over tenant data, canonical attributes or equipment compatibility. Existing private uploads, import candidates, immutable review records and transactional application already implement the required human boundary.

Extend ImportJob with a mode, original-source reference, request identity and extraction metadata; extend Candidate with extraction provenance. Do not duplicate evidence/review/assessment models. AI jobs reuse private bytes and existing target/claim comparison and apply services. Only existing product/package targets are allowed initially. Scope triggers supplement current membership and transaction checks.

Use a small replaceable provider protocol, one optional pinned OpenAI SDK adapter and strict application schemas. Credentials stay in the secure backend environment; activation is off by default and requires an explicit source-transmission action. No tools, client-selected URLs/models, automatic retries, provider storage request or direct catalog/rule/assessment mutation is permitted. Source text is untrusted data separated from extraction instructions. Exact quote/segment/value-unit validation precedes deterministic Decimal normalization; unknown/ungrounded claims are quarantined. Human corrections preserve original values and rationale.

Persist a processing lease before provider work; do not hold tenant locks during the call. Recheck authority/source/targets/lease during atomic finish. Bound source/output, attempts, timeout, active work and rate. Explicit retry/cancel/recovery fit the current synchronous monolith; no queue infrastructure is added. Duplicate candidate persistence is prevented, but interrupted external requests cannot guarantee exactly-once provider billing. Owner/admin approval and explicit canonical selection use existing services. Frozen assessment provenance gains AI metadata; the Phase 5 evaluator is unchanged.

Tradeoffs: conservative rejection of ambiguous units/locations, synchronous worker occupancy, optional SDK deployment and residual semantic/prompt-injection risks. Quoted text is evidence support, not authenticity or physical verification. Tests use mocked responses and actual SDK in-memory HTTP transport. Live model quality, provider retention/access and hardware safety require separately authorized verification. See the [operating guide](../ai-extraction-api.md).
