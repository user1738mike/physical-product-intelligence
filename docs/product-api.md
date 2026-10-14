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

Collections use `?page=1`, with 25 results and `count`, `next`, `previous`, `results`. Product ordering is SKU then UUID, revision ordering descending number, evidence ordering newest recorded time, and packaging ordering level then UUID. Follow page numbers through the same-origin collection path; the backend's absolute pagination links can contain its internal host. There are no filtering/search, bulk-write or file-download APIs in this phase. Each revision is a complete replacement snapshot for new history: omitted optional fields reset to blank/unknown rather than inheriting prior data. Earlier revisions remain unchanged.

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

Products always have a first revision. New revisions receive the next number transactionally, including concurrent submissions. Evidence, revisions, profiles, observations and revision/source links cannot be edited or deleted through the API; no generic product PATCH/DELETE exists. Owner/admin archival disables new revisions/evidence without hiding authorized history. Reactivation permits new submissions. Tenant suspension denies access and membership removal affects subsequent requests. Audit events contain product/revision/evidence IDs and actions rather than source text, measurements, digests or credentials.

The [OpenAPI document](/api/v1/schema/) is generated from request/response serializers. ADR 0007 records model and policy decisions. Product editing screens, captured artifact storage, sampling protocols, preferred-observation selection, constraints and assessments remain future work.
