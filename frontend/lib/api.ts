export type User = { id: number; username: string };
export type Role = "owner" | "admin" | "member";
export type Organization = {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
};
export type Membership = {
  id: string;
  user: User;
  role: Role;
  organization: Organization;
};
export type Page<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
export type Member = Omit<Membership, "organization">;
export type AuditEvent = {
  id: string;
  timestamp: string;
  actor_id: number | null;
  action: string;
  target_type: string;
  target_id: string;
  outcome: "success" | "failure";
  metadata: Partial<Record<"role" | "previous_role", Role>>;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// Fetch a masked token for each mutation: login rotates Django's CSRF secret.
// Neither the token nor the session is persisted in browser storage.
export async function request<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  if (!path.startsWith("/api/v1/") || path.split("?")[0].includes("..")) {
    throw new Error("Unsupported API path");
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    const tokenResponse = await fetch("/api/v1/auth/csrf/", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!tokenResponse.ok)
      throw new ApiError(
        tokenResponse.status,
        "Could not prepare a secure request.",
      );
    const token: { csrfToken: string } = await tokenResponse.json();
    headers["X-CSRFToken"] = token.csrfToken;
    if (data !== undefined && !(data instanceof FormData))
      headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers,
    ...(data === undefined
      ? {}
      : { body: data instanceof FormData ? data : JSON.stringify(data) }),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => null);
    let message =
      "Request failed. Check your input and access, then try again.";
    if (problem && typeof problem === "object") {
      const collect = (value: unknown): string[] => {
        if (typeof value === "string") return [value];
        if (Array.isArray(value)) return value.flatMap(collect);
        if (value && typeof value === "object")
          return Object.values(value).flatMap(collect);
        return [];
      };
      const messages = collect(problem);
      if (messages.length) message = messages.join(" ");
    }
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  me: () => request<User>("/api/v1/auth/me/"),
  register: (username: string, password: string) =>
    request<User>("/api/v1/auth/register/", "POST", { username, password }),
  login: (username: string, password: string) =>
    request<User>("/api/v1/auth/login/", "POST", { username, password }),
  logout: () => request<void>("/api/v1/auth/logout/", "POST"),
  memberships: (page = 1) =>
    request<Page<Membership>>(`/api/v1/auth/memberships/?page=${page}`),
  createOrganization: (name: string, slug: string) =>
    request<Organization>("/api/v1/organizations/", "POST", { name, slug }),
  organization: (id: string) =>
    request<Organization>(`/api/v1/organizations/${encodeURIComponent(id)}/`),
  updateOrganization: (id: string, name: string) =>
    request<Organization>(
      `/api/v1/organizations/${encodeURIComponent(id)}/`,
      "PATCH",
      { name },
    ),
  setOrganizationActive: (id: string, is_active: boolean) =>
    request<Organization>(
      `/api/v1/organizations/${encodeURIComponent(id)}/state/`,
      "POST",
      { is_active },
    ),
  members: (id: string, page = 1) =>
    request<Page<Member>>(
      `/api/v1/organizations/${encodeURIComponent(id)}/members/?page=${page}`,
    ),
  member: (id: string, memberId: string) =>
    request<Member>(
      `/api/v1/organizations/${encodeURIComponent(id)}/members/${encodeURIComponent(memberId)}/`,
    ),
  addMember: (
    id: string,
    username: string,
    role: Exclude<Role, "owner"> = "member",
  ) =>
    request<Member>(
      `/api/v1/organizations/${encodeURIComponent(id)}/members/`,
      "POST",
      { username, role },
    ),
  changeRole: (id: string, memberId: string, role: Exclude<Role, "owner">) =>
    request<Member>(
      `/api/v1/organizations/${encodeURIComponent(id)}/members/${encodeURIComponent(memberId)}/`,
      "PATCH",
      { role },
    ),
  removeMember: (id: string, memberId: string) =>
    request<void>(
      `/api/v1/organizations/${encodeURIComponent(id)}/members/${encodeURIComponent(memberId)}/`,
      "DELETE",
    ),
  transferOwnership: (id: string, membership_id: string) =>
    request<Organization>(
      `/api/v1/organizations/${encodeURIComponent(id)}/transfer/`,
      "POST",
      { membership_id },
    ),
  audit: (id: string, page = 1) =>
    request<Page<AuditEvent>>(
      `/api/v1/organizations/${encodeURIComponent(id)}/audit/?page=${page}`,
    ),
};
