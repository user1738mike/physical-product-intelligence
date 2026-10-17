import { request } from "./api";

export const scopes = [
  "catalog:read",
  "assessments:read",
  "assessments:export",
] as const;
export type Credential = {
  id: string;
  name: string;
  scopes: string[];
  expires_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
};
export type Destination = {
  id: string;
  url: string;
  revision: number;
  enabled: boolean;
  subscriptions: string[];
  key_version: number;
  overlap_until: string | null;
};
export type Delivery = {
  id: string;
  event_id: string;
  destination_id: string;
  revision: number;
  state: string;
  attempts: number;
  diagnostic: string;
  status_code: number | null;
  replays: number;
  due_at: string;
};
export type Integrations = {
  outbound_available: boolean;
  credential_creation_available: boolean;
  allowances: { credentials: number; destinations: number };
  credentials: Credential[];
  destinations: Destination[];
  deliveries: Delivery[];
};
const root = (org: string) =>
  `/api/v1/organizations/${encodeURIComponent(org)}/integrations/`;
export const integrations = (org: string) => request<Integrations>(root(org));
export const createCredential = (
  org: string,
  value: {
    name: string;
    scopes: string[];
    expires_at: string;
    rotate?: string;
    revoke_old?: boolean;
  },
) =>
  request<Credential & { secret: string }>(
    root(org) + "credentials/",
    "POST",
    value,
  );
export const revokeCredential = (org: string, id: string) =>
  request<Credential>(
    root(org) + `credentials/${encodeURIComponent(id)}/revoke/`,
    "POST",
    {},
  );
export const saveDestination = (
  org: string,
  value: {
    url: string;
    subscriptions: string[];
    enabled: boolean;
    expected_revision?: number;
  },
  id?: string,
) =>
  request<Destination & { secret?: string }>(
    root(org) + "destinations/" + (id ? encodeURIComponent(id) + "/" : ""),
    id ? "PATCH" : "POST",
    value,
  );
export const rotateSigning = (org: string, id: string, immediate: boolean) =>
  request<Destination & { secret: string }>(
    root(org) + `destinations/${encodeURIComponent(id)}/rotate/`,
    "POST",
    { immediate },
  );
export const replayDelivery = (org: string, id: string) =>
  request<Delivery>(
    root(org) + `deliveries/${encodeURIComponent(id)}/replay/`,
    "POST",
    {},
  );
