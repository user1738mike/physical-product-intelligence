import { request, type Page } from "./api";
import type { Claim } from "./products";

export type EquipmentDefinition = {
  name: string;
  description: string;
  manufacturer: string;
  model: string;
  category: string;
  source_reference: string;
  operational_context: string;
  supported_levels: string[];
  orientation_notes: string;
  handling_notes: string;
};
export type Equipment = {
  id: string;
  organization_id: string;
  code: string;
  status: "draft" | "active" | "archived";
  version: number;
  revision: number;
  revision_id: string;
  definition: EquipmentDefinition;
  latest_rule_version: number | null;
  created_by_id: number | null;
  modified_by_id: number | null;
  created_at: string;
  updated_at: string;
};
export type SpecSource = {
  kind: "evidence" | "import";
  id: string;
  snapshot?: Record<string, unknown>;
};
export type Rule = {
  id: string;
  type:
    | "maximum"
    | "minimum"
    | "required_attribute"
    | "packaging_level"
    | "orientation";
  name: string;
  explanation: string;
  severity: "hard" | "advisory";
  enabled: boolean;
  attribute?: string;
  limit?: string;
  unit?: string;
  margin?: string;
  allowed?: string[];
  source_reference: string;
  source: SpecSource | null;
  version?: number;
  canonical_limit?: string;
  canonical_margin?: string;
  canonical_unit?: string;
};
export type RuleSet = {
  id: string;
  equipment_id: string;
  equipment_revision_id: string;
  number: number;
  name: string;
  rules: Rule[];
  evidence_policy: "reported_or_measured" | "measured_only";
  schema_version: string;
  reason: string;
  created_at: string;
  created_by_id: number | null;
  activation: {
    activated_at: string;
    activated_by_id: number | null;
    reason: string;
  } | null;
};
export type EquipmentRevision = {
  id: string;
  number: number;
  definition: EquipmentDefinition;
  reason: string;
  created_by_id: number | null;
  created_at: string;
};
export type RuleResult = {
  rule_id: string;
  rule_version: number;
  rule_set_version: number;
  name: string;
  type: string;
  severity: string;
  attribute: string;
  status: "pass" | "fail" | "indeterminate" | "not_applicable";
  reason: string;
  recorded_attribute?: string;
  recorded_value?: string | null;
  recorded_values?: Claim[];
  expected?: Record<string, unknown> | string[];
  source?: SpecSource | null;
  source_reference?: string;
  explanation?: string;
  used_claim_ids: string[];
};
export type AssessmentSummary = {
  id: string;
  product_id: string;
  packaging_id: string | null;
  equipment_id: string;
  equipment_revision_id: string;
  product_revision_id: string;
  rule_set_id: string;
  parent_id: string | null;
  created_by_id: number | null;
  created_at: string;
  engine_version: string;
  overall: "compatible" | "incompatible" | "indeterminate";
  summary: string;
};
export type Assessment = AssessmentSummary & {
  organization_id: string;
  request_id: string;
  packaging_revision_id: string | null;
  inputs: {
    product: {
      id: string;
      sku: string;
      name: string;
      latest_revision_number: number;
    };
    packaging: {
      id: string;
      name: string;
      level: string;
      version: number;
    } | null;
    orientation: string | null;
    handling_level: string | null;
    level_basis: string;
    attributes: Record<
      string,
      {
        claims: Claim[];
        conflicting: boolean;
        quality_status: string;
        selected_claim_id: string | null;
        selection: unknown;
      }
    >;
  };
  equipment_snapshot: {
    id: string;
    number: number;
    definition: EquipmentDefinition;
  };
  rule_snapshot: RuleSet;
  results: RuleResult[];
};
export const orgBase = (org: string) =>
  `/api/v1/organizations/${encodeURIComponent(org)}/`;
export const equipmentPath = (org: string) =>
  `/organizations/${encodeURIComponent(org)}/equipment`;
export const assessmentPath = (org: string) =>
  `/organizations/${encodeURIComponent(org)}/assessments`;
const encoded = (id: string) => encodeURIComponent(id);
const query = (values: Record<string, string | number | undefined>) =>
  new URLSearchParams(
    Object.entries(values)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();
export const compatibility = {
  equipment: (
    org: string,
    values: Record<string, string | number | undefined> = {},
  ) => request<Page<Equipment>>(orgBase(org) + `equipment/?${query(values)}`),
  profile: (org: string, id: string) =>
    request<Equipment>(orgBase(org) + `equipment/${encoded(id)}/`),
  createEquipment: (org: string, data: unknown) =>
    request<Equipment>(orgBase(org) + "equipment/", "POST", data),
  editEquipment: (org: string, id: string, data: unknown) =>
    request<Equipment>(
      orgBase(org) + `equipment/${encoded(id)}/`,
      "PATCH",
      data,
    ),
  state: (org: string, id: string, data: unknown) =>
    request<Equipment>(
      orgBase(org) + `equipment/${encoded(id)}/state/`,
      "POST",
      data,
    ),
  revisions: (org: string, id: string, page = 1) =>
    request<Page<EquipmentRevision>>(
      orgBase(org) + `equipment/${encoded(id)}/revisions/?page=${page}`,
    ),
  rules: (org: string, id: string, page = 1) =>
    request<Page<RuleSet>>(
      orgBase(org) + `equipment/${encoded(id)}/rule-sets/?page=${page}`,
    ),
  createRules: (org: string, id: string, data: unknown) =>
    request<RuleSet>(
      orgBase(org) + `equipment/${encoded(id)}/rule-sets/`,
      "POST",
      data,
    ),
  activate: (org: string, id: string, rule: string, data: unknown) =>
    request<RuleSet>(
      orgBase(org) +
        `equipment/${encoded(id)}/rule-sets/${encoded(rule)}/activate/`,
      "POST",
      data,
    ),
  assess: (org: string, data: unknown) =>
    request<Assessment>(orgBase(org) + "assessments/", "POST", data),
  assessments: (
    org: string,
    values: Record<string, string | number | undefined> = {},
  ) =>
    request<Page<AssessmentSummary>>(
      orgBase(org) + `assessments/?${query(values)}`,
    ),
  assessment: (org: string, id: string) =>
    request<Assessment>(orgBase(org) + `assessments/${encoded(id)}/`),
  compare: (org: string, id: string, other: string) =>
    request<{
      first_result: string;
      second_result: string;
      changes: {
        rule_id: string;
        before: RuleResult | null;
        after: RuleResult | null;
      }[];
    }>(
      orgBase(org) +
        `assessments/${encoded(id)}/compare/?other_id=${encoded(other)}`,
    ),
};
