import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import AuthForm from "../app/account/auth-form";
import type { Membership } from "../lib/api";
import { mergeMemberships } from "../lib/memberships";

function usernameInput(register: boolean) {
  const html = renderToStaticMarkup(
    <AuthForm
      register={register}
      busy={false}
      onSubmit={() => {}}
      onToggle={() => {}}
    />,
  );
  return html.match(/<input[^>]*name="username"[^>]*>/)?.[0] ?? "";
}

describe("account compatibility and organization context", () => {
  it("allows legacy Django usernames at login while retaining new-registration validation", () => {
    const login = usernameInput(false);
    expect(login).toContain('minLength="1"');
    expect(login).not.toContain("pattern=");
    const registration = usernameInput(true);
    const pattern = registration.match(/pattern="([^"]+)"/)?.[1];
    expect(pattern).toBeDefined();
    const validation = new RegExp(`^(?:${pattern})$`, "v");
    expect(validation.test("new.person-1")).toBe(true);
    expect(validation.test("legacy+name@example.com")).toBe(false);
    expect(validation.test("用户")).toBe(false);
  });

  it("keeps the new organization visible without duplicating it when later pages arrive", () => {
    const membership = (id: string): Membership => ({
      id,
      user: { id: 1, username: "person" },
      role: "owner",
      organization: { id: `org-${id}`, name: id, slug: id, is_active: true },
    });
    const firstPage = Array.from({ length: 25 }, (_, index) =>
      membership(String(index)),
    );
    const created = membership("new");
    const visible = mergeMemberships(firstPage, [created]);
    const nextPage = mergeMemberships(visible, [created]);
    expect(nextPage).toHaveLength(26);
    expect(
      nextPage.find((item) => item.organization.id === created.organization.id),
    ).toEqual(created);
    expect(firstPage).toHaveLength(25);
  });

  it("refreshes server roles rather than preserving a stale owner claim", () => {
    const previous: Membership = {
      id: "membership",
      user: { id: 1, username: "person" },
      role: "owner",
      organization: { id: "org", name: "Org", slug: "org", is_active: true },
    };
    const changed: Membership = { ...previous, role: "member" };
    expect(mergeMemberships([previous], [changed])).toEqual([changed]);
    expect(previous.role).toBe("owner");
  });
});
