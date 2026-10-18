import { request } from "./api";

export type Meter = {
  definition: string;
  limit: number | null;
  used: number;
  reserved: number;
  remaining: number | null;
};
export type Commercial = {
  status: "active" | "suspended" | "expired" | "unassigned";
  plan: {
    code: string;
    version: number;
    name: string;
    features: Record<string, boolean>;
  } | null;
  starts_at: string | null;
  ends_at: string | null;
  period_start: string;
  period_end: string;
  metering_started_at: string | null;
  historical_usage_complete: boolean;
  meters: Record<"active_products" | "assessments" | "extractions", Meter>;
  history: {
    id: string;
    plan_code: string;
    plan_version: number;
    starts_at: string;
    ends_at: string | null;
    status: string;
    source: string;
  }[];
};

export const commercial = (org: string) =>
  request<Commercial>(
    `/api/v1/organizations/${encodeURIComponent(org)}/commercial/`,
  );
