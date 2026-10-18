import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { TenantFrame } from "../app/products/ui";
import { TenantContext, WorkspaceContext } from "../app/dashboard/context";
import {
  currentSection,
  organizationPath,
  visibleSections,
} from "../lib/workspace";
import type { Membership } from "../lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/organizations/a/products",
}));

const member: Membership = {
  id: "membership",
  role: "member",
  user: { id: 1, username: "fixture-user" },
  organization: {
    id: "a",
    name: "Fixture lab",
    slug: "fixture-lab",
    is_active: true,
  },
};

function renderFrame(
  membership: Membership,
  org = "a",
  allowInactiveOrganization = false,
) {
  return renderToStaticMarkup(
    <WorkspaceContext.Provider value={{ org: "a" }}>
      <TenantContext.Provider value={membership}>
        <TenantFrame
          org={org}
          allowInactiveOrganization={allowInactiveOrganization}
        >
          <h1>Authorized record</h1>
        </TenantFrame>
      </TenantContext.Provider>
    </WorkspaceContext.Provider>,
  );
}

describe("organization dashboard boundaries", () => {
  it("reuses the layout context without nesting another navigation or main", () => {
    const html = renderFrame(member);
    expect(html).toContain("Authorized record");
    expect(html).not.toContain("<main");
    expect(html).not.toContain("<nav");
  });

  it("does not render a new organization's records under an old context", () => {
    const html = renderFrame(member, "b");
    expect(html).not.toContain("Authorized record");
    expect(html).not.toContain("Fixture lab");
    expect(html).toContain("Loading your organization");
  });

  it("preserves the explicit inactive management paths without exposing business records", () => {
    const inactive = {
      ...member,
      organization: { ...member.organization, is_active: false },
    };
    const denied = renderFrame(inactive);
    expect(denied).toContain("Organization suspended");
    expect(denied).toContain("/organizations/a/settings");
    expect(denied).not.toContain("Authorized record");
    expect(renderFrame(inactive, "a", true)).toContain("Authorized record");
  });

  it("keeps restricted navigation out of the member menu and retains deep-link section identity", () => {
    const labels = visibleSections("member").map((item) => item.label);
    expect(labels).toContain("Organization settings");
    expect(labels).not.toContain("Billing history");
    expect(labels).not.toContain("Plan and usage");
    expect(labels).not.toContain("Integrations");
    expect(visibleSections("admin")).toHaveLength(9);
    expect(currentSection("/organizations/a/products/record/edit").label).toBe(
      "Products",
    );
    expect(organizationPath("a", "dashboard")).toBe(
      "/organizations/a/dashboard",
    );
  });
});
