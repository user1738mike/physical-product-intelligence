# Product and packaging API guide

Phase 3 exposes structured records through Django/DRF and the same-origin Next.js proxy. Use the existing registration/login/CSRF session flow. Obtain `/api/v1/auth/csrf/` and send the returned masked token as `X-CSRFToken` with every mutation, including bodyless mutations. Never place session or CSRF secrets in browser storage. All responses, including denials, are non-cacheable.

Let `base=/api/v1/organizations/{organization_id}/products/`. UUIDs in paths must belong to the authenticated organization and their enclosing product/revision. A foreign, unknown or inaccessible resource returns 404; anonymous/role/CSRF denial returns 403. Staff has no bypass. JSON payloads reject unrecognized or system-owned fields. Duplicate SKUs return 409; malformed values and writes to archived products return 400. Historical PATCH/DELETE is unsupported (405).

| Method | Path relative to base | Behavior |
| --- | --- | --- |
| GET / POST | empty | Paginated product collection / create identity and revision 1 atomically |
| GET | `{product_id}/` | Identity, organization ID, SKU, active state, latest revision number and timestamps |
| POST | `{product_id}/state/` | Owner/admin archive or reactivate using `{"is_active":false}` or true |
| GET / POST | `{product_id}/revisions/` | Paginated full snapshots newest first / append a complete snapshot |
| GET | `{product_id}/revisions/{revision_id}/` | One immutable full product/packaging snapshot |
| GET / POST | `{product_id}/evidence/` | Paginated provenance records / append immutable metadata |
| GET | `{product_id}/evidence/{evidence_id}/` | One provenance record |
| GET | `{product_id}/revisions/{revision_id}/packaging/` | Paginated packaging profiles with observations |
| GET | `{product_id}/revisions/{revision_id}/packaging/{packaging_id}/` | One profile with observations |

Collections use `?page=1`, with 25 results and `count`, `next`, `previous`, `results`. Product ordering defaults to SKU then UUID. Catalog queries accept `search` (SKU/current name, at most 100 characters), `status=all|active|archived` and `ordering=sku|-sku|name|-name|updated_at|-updated_at`. Unsupported query fields/orderings and invalid or excessive page numbers are rejected. Revision ordering is descending number; evidence is newest first. Follow page numbers through the same-origin collection path; backend absolute links can contain its internal host. Bulk writes and file downloads are unavailable. The original revision POST remains a complete snapshot replacement; the newer product PATCH below safely copies retained data and appends a revision.

## Create a product

Owners/admins/members can contribute. SKUs accept ASCII letters/digits/dot/underscore/hyphen, begin with a letter/digit and have at most 100 characters. They are case-sensitive and unique within the tenant; they cannot be reassigned. Name and change reason are required. Optional fields are description, brand, manufacturer, model_number, category, evidence_ids and packaging.

```json
{
  "sku": "BOX-001",
  "revision": {
    "name": "Example boxed item",
    "brand": "Example manufacturer",
    "category": "Customer-defined category",
    "description": "Manually entered reference record",
    "change_reason": "Initial product record"
  }
}
```

The response contains `id` and `latest_revision_number: 1`. Query its revisions collection to obtain the immutable revision UUID. Empty packaging means unknown, not an unpackaged or dimensionless product. A future new revision may add packaging/evidence.

## Record provenance

POST to the product's evidence collection. Attribution/license and observation time are required declarations by the contributor; use an explicit unknown/unconfirmed declaration when appropriate. This API does not verify those declarations. `source_reference` is plain metadata; a URL is never fetched. Source types are `manual`, `supplier_document`, `physical_test` and `other`. Observation times cannot be in the future. SHA-256 is optional; if supplied it must be 64 lowercase hexadecimal characters and is explicitly unverified.

```json
{
  "title": "Manual scale observation",
  "source_type": "manual",
  "source_reference": "Internal notebook, entry 17",
  "description": "Mass observation for one packaged unit",
  "attribution": "Contributor's declared observer",
  "license": "Internal use declared; rights not independently verified",
  "observed_at": "2026-01-01T10:00:00Z"
}
```

The response includes the evidence UUID, `capture_status: "reference_only"`, server recording time and recording user ID. No file bytes, verified checksums, public media URLs, object keys or upload status are accepted. These references alone are not reproducible captured evidence. To correct a record, append new evidence and reference it in a new revision; prior evidence persists. Deleting a user nulls authorship references while preserving history.

## Append a packaging revision

Replace the example `evidence_id` below with the UUID just returned. All sources must belong to this product. Measurement sources are automatically added to the revision's evidence links; `evidence_ids` can additionally cite sources for qualitative product fields. Packaging is submitted with each revision, at most four distinct levels. A unit root is required when any profiles are provided; its quantity is 1 and it has no contained level. Inner/case/pallet may contain only a present smaller level. `quantity` is the count of the immediate contained level, not the total number of units.

```json
{
  "name": "Example boxed item",
  "brand": "Example manufacturer",
  "change_reason": "Record observed unit mass and case count",
  "packaging": [
    {
      "level": "unit",
      "quantity": 1,
      "material": "Contributor-declared cardboard carton",
      "fragile": null,
      "stackable": null,
      "measurements": [
        {
          "property": "mass",
          "value": "1250",
          "unit": "g",
          "lower": "1200",
          "upper": "1300",
          "method": "measured",
          "observed_at": "2026-01-01T10:00:00Z",
          "evidence_id": "00000000-0000-0000-0000-000000000000"
        }
      ]
    },
    {
      "level": "case",
      "contains_level": "unit",
      "quantity": 12
    }
  ]
}
```

The example converts exactly to 1.250000000 kg with enclosing bounds 1.200000000–1.300000000 kg, under conversion version `metric-v1`. Outputs retain original values/unit/bounds alongside canonical values/unit/bounds and evidence ID. Submit decimal strings, up to 12 integer and six fractional digits. Excess precision, nonfinite/nonpositive values, dimension mixing and partial or non-enclosing uncertainty bounds are rejected. Lower/upper bounds may both be omitted/null; that means uncertainty was not supplied. Bounds are declared intervals, not an inferred statistical confidence level.

Supported properties are length/width/height with mm/cm/m → mm, and mass with g/kg → kg. Methods are measured, supplier_specification and manual_transcription. At most 50 observations per profile and 100 explicit evidence references are allowed. The proxy caps the complete request body at 64 KiB. Multiple competing observations for one property remain distinct; no preferred observation or handling safety judgment is computed. Missing properties stay absent and nullable traits stay unknown.

## History, archival and boundaries

Products always have a first revision. New revisions receive the next number transactionally, including concurrent submissions. Historical evidence, revisions, bundled profiles, observations and revision/source links cannot be edited or deleted. Product PATCH now appends a revision with concurrency validation; product DELETE remains unavailable. Owner/admin archival stops new writes while retaining history. Tenant suspension denies access and membership removal affects subsequent requests. Audit events contain actions/IDs, not source text, physical values, digests or credentials.

The [OpenAPI document](/api/v1/schema/) is generated from request/response serializers. ADRs 0007/0008 record model and policy decisions. Product screens and explicit claim selection are implemented below. Captured artifacts, automated sampling protocols, constraints and assessments remain future work.

## Current catalog and packaging workflows

The browser entry point is `/products`. Choose an organization, search/page the catalog, and open/create a product. The product page provides editing, packaging profiles, attribute claims, lifecycle controls and scoped history. Owners/admins see physical verification and selection controls; members can contribute reported/estimated claims and read history. All permissions are rechecked server-side.

`PATCH {product_id}/` accepts one or more descriptive fields, `expected_revision` and `change_reason`. Example: `{"name":"Corrected name","expected_revision":2,"change_reason":"Correct source transcription"}`. It retains prior source links/packaging snapshots and appends revision 3. A stale expected revision returns 409. It cannot change SKU, tenant ownership, actors or lifecycle state. The separate state endpoint remains owner/admin-only. Catalog details/author fields are derived from revisions; `modified_by_id` means the latest catalog revision author, while lifecycle actors are in history.

The original `/revisions/{id}/packaging/` routes above are immutable bundled snapshot history. The current editable packaging routes are separate stable identities, allowing multiple configurations at the same level:

| Method | Relative route | Behavior |
| --- | --- | --- |
| GET / POST | `{product_id}/packaging/` | List/create live named configurations |
| GET / PATCH | `{product_id}/packaging/{packaging_id}/` | Retrieve/edit descriptors with `expected_version` and `change_reason` |
| POST | `{product_id}/packaging/{packaging_id}/state/` | Owner/admin lifecycle change with `expected_version` and `is_active` |
| GET | `{product_id}/packaging/{packaging_id}/revisions/` | Immutable complete descriptor/lifecycle history |
| GET | `{product_id}/packaging/{packaging_id}/evidence/` | Distinct provenance sources referenced by this profile's claims |

Create with `{"name":"Six-unit shipping case","level":"case","quantity":6,"material":"Cardboard"}`. Name is required/unique within its product; level is required. Optional quantity means declared units per package; null means unknown. Optional material/description are reported descriptors, not physical verification. No physical dimension/mass is inferred. Existing bundled snapshots are retained and are not automatically merged into live configurations. Edits increment the version and preserve the previous descriptor revision; stale updates return 409. Product or profile archival blocks further edits/claims/verification/selection until authorized reactivation.

## Attribute claims and authorized verification

Let `scope={product_id}/` for product attributes or `{product_id}/packaging/{packaging_id}/` for a live profile. Sources can be shared between claims of the same product; foreign-product sources are denied even within one tenant.

| Method | Relative route | Behavior |
| --- | --- | --- |
| GET / POST | `scope + claims/` | Paginated immutable assertions / add reported or estimated claim |
| GET | `scope + claims/{claim_id}/` | Claim, source and physical verification records |
| POST | `scope + claims/{claim_id}/verification/` | Owner/admin documented physical measurement; creates a separate measured claim |
| GET | `scope + attributes/` | Fixed nine-attribute state summary, conflicts and explicit selection |
| POST | `scope + attributes/{attribute}/selection/` | Owner/admin selection with rationale |
| GET | `scope + history/` | Authorized success history for this resource and its claims |

Numeric attributes are length/width/height/mass with the existing exact Decimal/unit/bounds validation. Text claims support name, brand, manufacturer, category and material via `text_value`; numeric fields/units are forbidden on text claims. Sources are supplied using exactly one of `evidence_id` or nested `source` (the Evidence POST shape). Nested source+claim writes are atomic. A resource retains up to 500 claims; writes beyond the cap fail explicitly without purging history.

```json
{
  "attribute": "mass",
  "basis": "estimated",
  "value": "1100",
  "unit": "g",
  "method": "External model or estimation method, version 1",
  "limitations": "No physical sample; not independently measured",
  "observed_at": "2026-01-01T10:00:00Z",
  "source": {
    "title": "Externally supplied estimate",
    "source_type": "ai_estimate",
    "source_reference": "External run reference",
    "attribution": "Contributor-declared operator",
    "license": "Unknown / not confirmed",
    "observed_at": "2026-01-01T10:00:00Z"
  }
}
```

Ordinary creation accepts reported/estimated only. Estimates require methodology and limitations; arbitrary confidence scalars are rejected, and AI sources cannot be relabeled as reported claims. No AI pipeline runs. A manually entered or contributor-described measured value remains unverified. The legacy snapshot observation response explicitly labels its verification status `unverified_report`.

Physical verification requires owner/admin, a numeric value with declared unit/time, physical_test evidence, instrument, procedure and sampling/limitation notes. Example body:

```json
{
  "value": "1.35", "unit": "kg",
  "observed_at": "2026-01-02T10:00:00Z",
  "instrument": "Contributor-declared scale reference",
  "procedure": "Tare the scale and weigh the sealed sample.",
  "notes": "One sample; no handling safety conclusion.",
  "source": {
    "title": "Physical weighing record", "source_type": "physical_test",
    "source_reference": "Notebook entry 17", "attribution": "Declared observer",
    "license": "Contributor-declared internal use",
    "observed_at": "2026-01-02T10:00:00Z"
  }
}
```

The original claim remains unchanged. The response is a new measured claim with an immutable verification linking original/new claim, authorized actor, server time, instrument/procedure/notes. This is a physical-measurement attestation, not independent verification of real-world truth or file integrity. It does not certify robot compatibility. Text claims cannot use the physical-measurement verification endpoint.

The summary distinguishes unknown, reported, estimated, verified, conflict and resolved. Absence is unknown, never zero. Different canonical values, intervals or text are competing claims. No canonical value is supplied until an owner/admin posts `{"claim_id":"...","rationale":"Why this observation is selected despite the competing evidence"}`. Selection never changes basis; a selected estimate remains estimated. A new contradictory claim after selection reopens the conflict and withholds the canonical value until renewed review. All claims, verifications and selection history are retained. Catalog text is not silently overwritten by a selection.

History has actor/time/action/resource identity, is paginated/non-cacheable and has no mutation/deletion endpoint. Members may read their product/profile history without global organization-audit permission. PostgreSQL deferred provenance guards supplement the same-product API checks and require a verification record for measured claims by commit. They do not provide RLS or database-level history immutability. SQLite cannot verify these PostgreSQL guards.

## Phase 4 ingestion increment

Evidence responses now optionally include `source_artifact` (job UUID, computed SHA-256, row/page location and an authorized relative download path), and capture_status `stored_private` for applied ingestion sources. Manual sources retain `reference_only`; declared digests remain unverified unless linked to a captured source. Import review/API routes are documented in [ingestion API](ingestion-api.md).
