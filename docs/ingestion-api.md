# Evidence ingestion API and operating guide

Organization root: `/api/v1/organizations/{organization_id}/imports/`. Use the existing session and fresh `X-CSRFToken` for every mutation. Same-origin Next.js transport preserves multipart boundaries, cookies, attachment headers and private/no-store responses. JSON bodies remain bounded at 64 KiB; only the import upload collection accepts multipart bodies up to 3 MiB at the proxy. Backend file size defaults to 2 MiB. Production ingress must enforce equivalent request/stream limits before Django.

| Method and relative route | Input / result |
| --- | --- |
| GET `limits/` | Current formats, canonical mapping fields and parser limits |
| GET collection | Paginated authorized jobs, newest first; `page` only |
| POST collection | Multipart `file`; creates uploaded job, returns 201 |
| GET `{job}/` | Status, versions, bounded preview, checksum, safe errors/counters, duplicate-upload warnings |
| POST `{job}/validate/` | expected_version, optional sheet, header_row (1–20), delimiter (``, comma, semicolon, tab, pipe); parses preview, never applies |
| POST `{job}/mapping/` | expected_version, mapping object from canonical field → exact source header; SKU required |
| POST `{job}/process/` | expected_version; creates source rows/candidates; repeat on awaiting_review returns same job |
| GET `{job}/rows/` | Paginated raw rows, location/errors, targets, creation permission and resulting source/product links |
| GET `{job}/candidates/` | Paginated candidates; allowlisted decision/quality filters and page |
| POST `{job}/candidates/{candidate}/review/` | expected_version (candidate), decision approve/reject, reason (5–1000 chars), optional corrected value/unit, select_value boolean for numeric claims only |
| POST `{job}/rows/{row}/creation/` | allow_create boolean, reason; explicit permission to create a previously absent SKU |
| POST `{job}/refresh/` | expected_version; current catalog comparison, resets candidate decisions to pending |
| POST `{job}/apply/` | expected_version; owner/admin atomic application of reviewed candidates |
| POST `{job}/cancel/` | expected_version; owner/admin cancellation retaining source/review history |
| GET `{job}/history/` | Paginated append-only review/correction/mapping records |
| GET `{job}/file/` | Authorized attachment of original bytes; integrity checked on every download |
| GET `{job}/errors/` | Authorized JSON attachment of bounded row/candidate errors and rejection decisions; no CSV formula-injection export |

Every resource, file, row, candidate, source and result is resolved through current active organization membership. Staff has no bypass. Members can upload/process/read; owner/admin alone changes review decisions, creation permissions, lifecycle and catalog. Unknown payload/query fields fail validation; no endpoint accepts a target product ID or tenant ID in the body. SKU lookup is always within the authorized organization. Errors: 400 validation, 403 session/CSRF/role/scanner policy, 404 inaccessible scoped resource, 409 stale version/state/target, 413 proxy body limit, 415 unsupported request media type, 429 throttle. Validation may return 200 with job status failed and a safe structured error; callers must inspect status.

## Formats and limits

Defaults: upload 2 MiB; 200 data rows after at most 20 preamble/header rows; 32 columns; 5 workbook sheets; 10 PDF pages; 2,000 characters per cell; 500,000 extracted characters; 128 archive entries; 8 MiB expanded XLSX; maximum compression ratio 100; parser timeout 20 seconds. Linux parser memory 512 MiB and CPU 10 seconds are hard process limits. Windows uses byte/text/archive/timeout bounds without Linux address-space enforcement. At most 20 unfinished jobs and 100 MiB retained source bytes per organization. Import creation/processing endpoints have a best-effort local-memory rate of 120/hour/user; production ingress/distributed limits remain necessary. Existing product-domain limits (500 claims/resource, 100 revision evidence references, precision limits) also apply and may atomically reject large imports into one resource.

All parser/storage limits are Django settings. Each `INGESTION_LIMITS` key supports `INGESTION_LIMIT_<UPPERCASE_KEY>` environment override. `INGESTION_MAX_BYTES`/`INGESTION_MAX_ROWS` are also accepted initial defaults. Keep proxy/ingress upload and timeout limits aligned when changing them. Increasing bounds requires load/resource review; limits are not throughput promises.

CSV accepts UTF-8 with/without BOM and BOM-marked UTF-16 LE/BE, strict quoting, escaped delimiters, explicit or safe delimiter detection. Unsupported encodings/control bytes, duplicate/empty headers and malformed quoting fail safely. Empty rows/cells remain absent, never erase catalog values. Unequal row widths produce row errors while other valid rows remain reviewable. Headers are limited to 80 characters.

XLSX supports selected sheet and header row, read-only parsing and real-cell iteration under explicit limits rather than trusting supplied dimensions. Duplicate headers, excessive sheets/rows/columns, ZIP traversal/duplicate entries, encryption, XML entities, macros, embedded objects, active controls and external relationships are rejected. Formula cells become `[UNSUPPORTED FORMULA]`; neither formulas nor cached results are executed/accepted as physical values. Exported reports are JSON attachments.

PDF/TXT extraction accepts anchored labels, one product per page: `SKU`, `Name`/`Product name`, `Manufacturer`, `Brand`, `Description`, `Package name`, `Package type`, `Material`, `Units per package`, `Length`, `Width`, `Height`, `Weight`/`Mass`. Example:

```text
SKU: BOX-001
Name: Shipping carton
Manufacturer: Example supplier
Package name: Outer case
Package type: case
Units per package: 6
Length: 300 mm
Width: 200 mm
Height: 150 mm
Weight: 1.35 kg
```

Dimensions on one PDF page must declare a common dimension unit; ambiguous mixed units require source correction/re-upload. Missing units are invalid. Multiple occurrences of the same field on one page mark the row ambiguous. No recognized text means a failed job, not invented values. Scans/OCR, arbitrary prose/table interpretation, DOC/DOCX, XLS/XLSM and password-protected documents are unsupported. PDF attachments and document open actions are rejected; source downloads remain inert attachments, not previews executed in the frontend.

## Mapping, review and application

Canonical mapping fields: sku, name, description, brand, manufacturer, package_name, package_type, material, quantity, length, width, height, mass, dimension_unit, mass_unit. Exact/limited alias suggestions require explicit confirmation. Every candidate preserves raw source value, original mapped row, location, normalized value/unit, parser version through its job, comparison snapshot, quality, decisions, corrections, reason/actor/time and result claim link. Numeric validation reuses Phase 3 Decimal precision, positivity and metric conversion. It never guesses units, confidence probabilities or physical verification. Unknown values have no candidate.

Candidate quality distinguishes new/equivalent/duplicate/conflict/invalid. Competing candidates and existing claims are visible. Different unit representations compare after exact canonical normalization. Existing conflicting values remain separate. Choose approve/reject individually; corrections preserve originals through immutable review records. Duplicate mapped rows must be rejected. A new product also needs creation permission and an approved name. Package-scoped rows require approval of package_name and a new package additionally requires package_type; units-per-package is optional. Existing package identity changes require a corrected source/new import rather than redirecting evidence to an unreviewed target.

All candidates must be decided before apply. Rejected/invalid rows remain visible and excluded; other explicitly approved values may apply, producing completed_with_errors and actual counters. The entire approved application is transactional; an unexpected domain/audit failure leaves no partial catalog writes. Conflicting approved descriptions or multiple different canonical selections for one target abort instead of choosing an order-dependent winner. Multiple numeric source assertions may all be accepted; only an explicit select_value with rationale selects the reported claim. Neither approval nor selection makes it measured. Existing verified claims are retained.

Apply checks expected catalog revisions, package versions and evidence snapshots under the organization lock. Stale data returns 409; refresh compares against current targets and invalidates decisions. Retry the same completed job to retrieve its result without new products/evidence/history. Uploading identical bytes creates another independently reviewed job, with duplicate warnings; checksum equality alone does not merge business data. No global reusable mapping presets are stored.

## Storage and production requirements

Local private root defaults to `backend/media/ingestion`, ignored by Git and outside frontend/static directories. Internal keys are generated UUIDs, never uploaded paths; no storage path/public URL is returned. Configure `INGESTION_STORAGE_ROOT` for private local storage. For a private object-storage implementation, supply a trusted Django storage backend through the `ingestion` alias, replacing its OPTIONS in deployment settings; object-store SDKs/credentials/encryption/policies are not installed. Never publish this root/bucket or use unauthenticated media routes.

Development/test explicitly allow unscanned files and show that state. Production rejects new uploads until `INGESTION_SCANNER` names a trusted callable `(bytes) -> True` that returns True only for inspected clean content; failures/False reject the upload. No antivirus engine/service is bundled or claimed. A production scanner must itself have time/resource limits. Build durable quarantine/scan outcomes, an isolated no-egress worker with bounded concurrency, durable queue/retry recovery, private encrypted storage, backups, retention/legal hold, orphan reconciliation and monitored operator access before general customer deployment. This development path is synchronous and not an OS sandbox. Uploaded bytes are never instructions to prompts/tools/configuration, and no AI provider/credentials or paid service is introduced.

Completion counters include accepted/rejected candidates, applied/rejected (fully skipped) rows, created/updated products and packaging, created claims and unresolved numeric attribute conflicts after explicit selections. Processing conflict counts describe detected candidates; unresolved_conflicts describes resulting applied catalog scopes.
