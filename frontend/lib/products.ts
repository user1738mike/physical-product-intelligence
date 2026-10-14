import { request, type AuditEvent, type Page } from "./api";

export type Product = {
  id: string;
  organization_id: string;
  sku: string;
  name: string;
  description: string;
  brand: string;
  manufacturer: string;
  model_number: string;
  category: string;
  is_active: boolean;
  latest_revision_number: number;
  latest_revision_id: string;
  creator_id: number | null;
  modified_by_id: number | null;
  created_at: string;
  updated_at: string;
};
export type ProductFields = Pick<
  Product,
  | "name"
  | "description"
  | "brand"
  | "manufacturer"
  | "model_number"
  | "category"
>;
export type Packaging = {
  id: string;
  product_id: string;
  name: string;
  level: "unit" | "inner" | "case" | "pallet";
  quantity: number | null;
  material: string;
  description: string;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  created_by_id: number | null;
  modified_by_id: number | null;
};
export type PackagingFields = Pick<
  Packaging,
  "name" | "level" | "quantity" | "material" | "description"
>;
export type PackagingRevision = PackagingFields & {
  id: string;
  version: number;
  is_active: boolean;
  change_reason: string;
  changed_by_id: number | null;
  recorded_at: string;
};
export const attributes = [
  "mass",
  "length",
  "width",
  "height",
  "name",
  "brand",
  "manufacturer",
  "category",
  "material",
] as const;
export type Attribute = (typeof attributes)[number];
export const numericAttributes: readonly string[] = [
  "mass",
  "length",
  "width",
  "height",
];
export type SourceType =
  | "manual"
  | "supplier_document"
  | "manufacturer_spec"
  | "imported_catalog"
  | "ai_estimate"
  | "physical_test"
  | "other";
export type SourceInput = {
  title: string;
  source_type: SourceType;
  source_reference: string;
  attribution: string;
  license: string;
  observed_at: string;
  description?: string;
};
export type Evidence = SourceInput & {
  id: string;
  product_id: string;
  capture_status: "reference_only" | "stored_private";
  source_artifact?: {
    job_id: string;
    sha256: string;
    location: string;
    download_path: string;
  } | null;
  declared_sha256: string;
  recorded_at: string;
  recorded_by_id: number | null;
};
export type Verification = {
  id: string;
  claim_id: string;
  measured_claim_id: string;
  verified_by_id: number | null;
  verified_at: string;
  instrument: string;
  procedure: string;
  notes: string;
};
export type Claim = {
  id: string;
  product_id: string;
  packaging_id: string | null;
  attribute: Attribute;
  basis: "reported" | "estimated" | "measured";
  value: string | null;
  unit: string;
  lower: string | null;
  upper: string | null;
  canonical_value: string | null;
  canonical_unit: string;
  canonical_lower: string | null;
  canonical_upper: string | null;
  text_value: string;
  conversion_version: string;
  method: string;
  limitations: string;
  observed_at: string;
  recorded_at: string;
  recorded_by_id: number | null;
  evidence: Evidence;
  verification_record: Verification | null;
  verifications: Verification[];
};
export type ClaimInput = {
  attribute: Attribute;
  basis: "reported" | "estimated";
  value?: string | null;
  unit?: string;
  lower?: string | null;
  upper?: string | null;
  text_value?: string;
  method: string;
  limitations: string;
  observed_at: string;
  source: SourceInput;
};
export type VerificationInput = {
  value: string;
  unit: string;
  lower?: string | null;
  upper?: string | null;
  observed_at: string;
  instrument: string;
  procedure: string;
  notes: string;
  source: SourceInput;
};
export type Selection = {
  id: string;
  claim_id: string;
  selected_by_id: number | null;
  selected_at: string;
  rationale: string;
};
export type AttributeState = {
  attribute: Attribute;
  status:
    "unknown" | "reported" | "estimated" | "verified" | "conflict" | "resolved";
  claim_count: number;
  conflicting: boolean;
  selected_claim: Claim | null;
  selection: Selection | null;
};

const part = (value: string) => encodeURIComponent(value);
export const catalogPath = (org: string) =>
  `/organizations/${part(org)}/products`;
const base = (org: string) => `/api/v1/organizations/${part(org)}/products/`;
const productPath = (org: string, id: string) => `${base(org)}${part(id)}/`;
const scope = (org: string, id: string, packaging?: string) =>
  `${productPath(org, id)}${packaging ? `packaging/${part(packaging)}/` : ""}`;
export const claimValue = (claim: Claim) =>
  claim.value === null ? claim.text_value : `${claim.value} ${claim.unit}`;
export const claimLabel = (claim: Claim) =>
  claim.basis === "measured"
    ? "Physically verified (attested)"
    : claim.basis === "estimated"
      ? "Estimated — not verified"
      : "Reported — not verified";

export const products = {
  list: (
    org: string,
    params: {
      search?: string;
      status?: string;
      ordering?: string;
      page?: number;
    } = {},
  ) => {
    const query = new URLSearchParams(
      Object.entries(params).map(([key, value]) => [key, String(value)]),
    );
    return request<Page<Product>>(`${base(org)}?${query}`);
  },
  get: (org: string, id: string) => request<Product>(productPath(org, id)),
  create: (org: string, sku: string, fields: ProductFields, reason: string) =>
    request<Product>(base(org), "POST", {
      sku,
      revision: { ...fields, change_reason: reason },
    }),
  edit: (
    org: string,
    id: string,
    fields: ProductFields,
    revision: number,
    reason: string,
  ) =>
    request<Product>(productPath(org, id), "PATCH", {
      ...fields,
      expected_revision: revision,
      change_reason: reason,
    }),
  state: (org: string, id: string, is_active: boolean) =>
    request<Product>(productPath(org, id) + "state/", "POST", { is_active }),
  packaging: (org: string, id: string, page = 1) =>
    request<Page<Packaging>>(productPath(org, id) + `packaging/?page=${page}`),
  packagingGet: (org: string, id: string, pack: string) =>
    request<Packaging>(scope(org, id, pack)),
  packagingCreate: (org: string, id: string, fields: PackagingFields) =>
    request<Packaging>(productPath(org, id) + "packaging/", "POST", fields),
  packagingEdit: (
    org: string,
    id: string,
    pack: Packaging,
    fields: PackagingFields,
    reason: string,
  ) =>
    request<Packaging>(scope(org, id, pack.id), "PATCH", {
      ...fields,
      expected_version: pack.version,
      change_reason: reason,
    }),
  packagingState: (
    org: string,
    id: string,
    pack: Packaging,
    is_active: boolean,
  ) =>
    request<Packaging>(scope(org, id, pack.id) + "state/", "POST", {
      is_active,
      expected_version: pack.version,
    }),
  packagingRevisions: (org: string, id: string, pack: string, page = 1) =>
    request<Page<PackagingRevision>>(
      scope(org, id, pack) + `revisions/?page=${page}`,
    ),
  claims: (org: string, id: string, pack?: string, page = 1) =>
    request<Page<Claim>>(scope(org, id, pack) + `claims/?page=${page}`),
  claim: (org: string, id: string, claim: string, pack?: string) =>
    request<Claim>(scope(org, id, pack) + `claims/${part(claim)}/`),
  addClaim: (org: string, id: string, data: ClaimInput, pack?: string) =>
    request<Claim>(scope(org, id, pack) + "claims/", "POST", data),
  verify: (
    org: string,
    id: string,
    claim: string,
    data: VerificationInput,
    pack?: string,
  ) =>
    request<Claim>(
      scope(org, id, pack) + `claims/${part(claim)}/verification/`,
      "POST",
      data,
    ),
  attributes: (org: string, id: string, pack?: string) =>
    request<{ results: AttributeState[] }>(
      scope(org, id, pack) + "attributes/",
    ),
  select: (
    org: string,
    id: string,
    attribute: Attribute,
    claim_id: string,
    rationale: string,
    pack?: string,
  ) =>
    request<Selection>(
      scope(org, id, pack) + `attributes/${part(attribute)}/selection/`,
      "POST",
      { claim_id, rationale },
    ),
  history: (org: string, id: string, pack?: string, page = 1) =>
    request<Page<AuditEvent>>(scope(org, id, pack) + `history/?page=${page}`),
};
