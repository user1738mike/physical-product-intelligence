import { request, type Page } from "./api";

export const fields = [
  "sku",
  "name",
  "description",
  "brand",
  "manufacturer",
  "package_name",
  "package_type",
  "material",
  "quantity",
  "length",
  "width",
  "height",
  "mass",
  "dimension_unit",
  "mass_unit",
];
export const importsPath = (org: string) =>
  `/organizations/${encodeURIComponent(org)}/imports`;
export const importsApiPath = (org: string) =>
  `/api/v1/organizations/${encodeURIComponent(org)}/imports/`;
export type ImportJob = {
  mode?: "deterministic" | "ai";
  source_job_id?: string | null;
  extraction?: {
    provider: string;
    model: string;
    schema_version: string;
    attempts: number;
    retryable: boolean;
    stage: string;
    duration_ms?: number;
  };
  id: string;
  display_name: string;
  status: string;
  version: number;
  format: string;
  sha256: string;
  scan_status: string;
  parser_version: string;
  mapping: Record<string, string>;
  counters: Record<string, number>;
  errors: { code: string; message: string }[];
  duplicate_upload_ids: string[];
  preview: {
    headers?: string[];
    sheets?: string[];
    suggestions?: Record<string, string>;
    sample?: {
      location: string;
      cells: Record<string, string>;
      errors: string[];
    }[];
    row_count?: number;
  };
};
export type Candidate = {
  extraction?: {
    method: string;
    provider: string;
    model: string;
    schema_version: string;
    extracted_at: string;
    source_job_id: string;
    source_sha256: string;
    segment: number | null;
    quote: string;
    grounded: boolean;
    validation: string;
    confidence: null;
  };
  id: string;
  row_id: string;
  sku: string;
  location: string;
  field: string;
  raw_value: string;
  proposed: {
    value: string;
    unit: string;
    competing?: Record<string, unknown>[];
  };
  normalized: {
    value?: string | number;
    unit?: string;
    canonical_value?: string;
    canonical_unit?: string;
  };
  existing: Record<string, unknown>[];
  quality: string;
  errors: string[];
  decision: string;
  select_value: boolean;
  reason: string;
  reviewed_by_id: number | null;
  reviewed_at: string | null;
  version: number;
  claim_id: string | null;
};
export type ImportRow = {
  id: string;
  number: number;
  location: string;
  sku: string;
  product_id: string | null;
  errors: string[];
  allow_create: boolean;
  applied: boolean;
  evidence_id: string | null;
};
export type ReviewRecord = {
  id: string;
  action: string;
  actor_id: number | null;
  at: string;
  reason: string;
};
export type AICapability = {
  available: boolean;
  reason: string;
  schema_version: string;
  max_candidates: number;
  max_text_chars: number;
  privacy_notice: string;
};
export const ingestion = {
  aiCapability: (org: string) =>
    request<AICapability>(importsApiPath(org) + "ai-capabilities/"),
  startExtraction: (org: string, source: string, data: unknown) =>
    request<ImportJob>(
      importsApiPath(org) + `${encodeURIComponent(source)}/extractions/`,
      "POST",
      data,
    ),
  limits: (org: string) =>
    request<{ formats: string[]; limits: Record<string, number> }>(
      importsApiPath(org) + "limits/",
    ),
  jobs: (org: string, page = 1) =>
    request<Page<ImportJob>>(importsApiPath(org) + `?page=${page}`),
  job: (org: string, id: string) =>
    request<ImportJob>(importsApiPath(org) + `${encodeURIComponent(id)}/`),
  upload: (org: string, file: File) => {
    const data = new FormData();
    data.set("file", file);
    return request<ImportJob>(importsApiPath(org), "POST", data);
  },
  action: (org: string, id: string, action: string, data: unknown) =>
    request<ImportJob>(
      importsApiPath(org) + `${encodeURIComponent(id)}/${action}/`,
      "POST",
      data,
    ),
  rows: (org: string, id: string, page = 1) =>
    request<Page<ImportRow>>(
      importsApiPath(org) + `${encodeURIComponent(id)}/rows/?page=${page}`,
    ),
  candidates: (
    org: string,
    id: string,
    page = 1,
    decision = "",
    quality = "",
  ) =>
    request<Page<Candidate>>(
      importsApiPath(org) +
        `${encodeURIComponent(id)}/candidates/?page=${page}${decision ? `&decision=${encodeURIComponent(decision)}` : ""}${quality ? `&quality=${encodeURIComponent(quality)}` : ""}`,
    ),
  review: (org: string, id: string, candidate: string, data: unknown) =>
    request<Candidate>(
      importsApiPath(org) +
        `${encodeURIComponent(id)}/candidates/${encodeURIComponent(candidate)}/review/`,
      "POST",
      data,
    ),
  creation: (
    org: string,
    id: string,
    row: string,
    allow_create: boolean,
    reason: string,
  ) =>
    request<ImportRow>(
      importsApiPath(org) +
        `${encodeURIComponent(id)}/rows/${encodeURIComponent(row)}/creation/`,
      "POST",
      { allow_create, reason },
    ),
  history: (org: string, id: string, page = 1) =>
    request<Page<ReviewRecord>>(
      importsApiPath(org) + `${encodeURIComponent(id)}/history/?page=${page}`,
    ),
};
