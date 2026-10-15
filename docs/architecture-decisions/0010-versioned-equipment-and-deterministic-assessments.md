# ADR 0010: Versioned equipment and deterministic assessment snapshots

Status: accepted for Phase 5, 2026-10-15.

Equipment definitions, documented constraints and physical product observations evolve independently. A historical fit conclusion must retain its exact operands and cannot be silently reinterpreted using a later rule or favorable claim selection.

Add one compatibility module to the existing Django monolith. Reuse organizations, authorization/locks, audit events, products, packaging, claims, verification and private import provenance. Equipment has a stable identity and immutable specification revisions. Rules are allowlisted declarative JSON inside immutable numbered sets bound to one specification; separate activation records capture approval. Changing a specification makes prior sets ineligible for new evaluation. No expression language, shared equipment hierarchy or new infrastructure is needed.

A pure Decimal engine consumes frozen inputs. Explicit level/orientation, qualifying evidence and complete hard dimensional/mass envelope coverage are prerequisites for compatible. Reliable hard failure takes precedence; otherwise missing/conflicting evidence yields indeterminate. Estimates do not qualify, and editorial selections do not erase disagreement. Partial rule sets remain useful to explain failure/unknown results. Advisory checks are visible but nonbinding.

One transactional service captures actor, time, product/package/specification revisions, provenance, original/normalized operands, rule definitions, results and semantic version identifiers. Tenant-scoped idempotency keys preserve retry results. Same-target parents and stable rule IDs support comparisons of retained results. Ordinary APIs cannot mutate/delete history. PostgreSQL deferred reference guards supplement services, not RLS or protection against privileged operators.

The cost is bounded snapshot duplication and conservative indeterminate results. The gain is explicit evidence sufficiency and understandable history without executing historical code. Future semantics require a new engine/schema version; historical snapshots stay unchanged. Static recorded-input compatibility does not certify hardware safety or actual handling success. Detailed rules, resource bounds and API lifecycle are in the [guide](../compatibility-api.md).
