import { request } from "./api";

export type Statement = {
  id: string;
  status: string;
  settlement_status: string;
  period_start: string;
  period_end: string;
  currency: string;
  exponent: number;
  total_minor: string;
  original_total_minor: string;
  settled_minor: string;
  remaining_minor: string;
  snapshot: Record<string, unknown>;
  mode: "test" | "live";
  access_fulfilled: boolean;
  download_path: string;
  corrections: { id: string; delta_minor: string; created_at: string }[];
  settlements: {
    id: string;
    kind: string;
    amount_minor: string;
    created_at: string;
  }[];
};
export type Billing = {
  collection_available: boolean;
  statements: Statement[];
  operations: {
    id: string;
    statement_id: string;
    status: string;
    amount_minor: string;
    currency: string;
    expires_at: string;
  }[];
  unapplied_credit: Record<string, string>;
};
export const billing = (org: string) =>
  request<Billing>(`/api/v1/organizations/${encodeURIComponent(org)}/billing/`);
export const billingStatement = (org: string, id: string) =>
  request<Statement>(
    `/api/v1/organizations/${encodeURIComponent(org)}/billing/statements/${encodeURIComponent(id)}/`,
  );

export function money(minor: string, currency: string, exponent: number) {
  if (
    !/^-?\d+$/.test(minor) ||
    !/^[A-Z]{3}$/.test(currency) ||
    !Number.isInteger(exponent) ||
    exponent < 0 ||
    exponent > 3
  )
    return "Amount unavailable";
  const number = BigInt(minor),
    absolute = number < BigInt(0) ? -number : number,
    divisor = BigInt(10) ** BigInt(exponent);
  return `${currency} ${number < BigInt(0) ? "-" : ""}${(absolute / divisor).toString()}${exponent ? "." + (absolute % divisor).toString().padStart(exponent, "0") : ""}`;
}
