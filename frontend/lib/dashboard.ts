import { request, type Organization, type Role } from "./api";

export type Dashboard = {
  generated_at: string;
  scope: "all_time";
  organization: Organization;
  role: Role;
  products: { total: number; active: number; archived: number };
  imports: {
    total: number;
    by_status: Record<string, number>;
    awaiting_review: number;
    attention: number;
    recent: {
      id: string;
      display_name: string;
      status: string;
      created_at: string;
    }[];
  };
  equipment: {
    total: number;
    draft: number;
    active: number;
    archived: number;
    active_with_activated_rules: number;
  };
  assessments: {
    total: number;
    compatible: number;
    incompatible: number;
    indeterminate: number;
    recent: {
      id: string;
      product_id: string;
      equipment_id: string;
      overall: string;
      created_at: string;
      summary: string;
    }[];
  };
};

export const dashboard = (org: string) =>
  request<Dashboard>(
    `/api/v1/organizations/${encodeURIComponent(org)}/dashboard/`,
  );

export type DashboardResource<T> =
  | { scope: string; status: "loading" }
  | { scope: string; status: "ready"; data: T }
  | { scope: string; status: "error"; error: string };

// Each subscription belongs to one workspace and authorization scope. Cleanup
// prevents a slow request from publishing after navigation, retry or unmount.
export function loadDashboardResource<T>(
  scope: string,
  read: () => Promise<T>,
  publish: (state: DashboardResource<T>) => void,
  message: (error: unknown) => string,
) {
  let live = true;
  publish({ scope, status: "loading" });
  const done = Promise.resolve()
    .then(read)
    .then(
      (data) => {
        if (live) publish({ scope, status: "ready", data });
      },
      (error: unknown) => {
        if (live) publish({ scope, status: "error", error: message(error) });
      },
    );
  return {
    done,
    cancel: () => {
      live = false;
    },
  };
}
