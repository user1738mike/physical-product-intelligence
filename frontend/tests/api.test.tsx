import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import Account from "../app/account/account";
import { api, ApiError, request } from "../lib/api";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

afterEach(() => vi.unstubAllGlobals());

describe("session API boundary", () => {
  it("sends a fresh CSRF token and same-origin cookies for each mutation", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(Response.json({ csrfToken: "masked-first" }))
      .mockResolvedValueOnce(Response.json({ id: 1, username: "person" }))
      .mockResolvedValueOnce(Response.json({ csrfToken: "masked-rotated" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    await api.login("person", "fixture-only");
    await api.logout();
    expect(fetch.mock.calls[1][1]).toMatchObject({
      credentials: "same-origin",
      cache: "no-store",
      headers: { "X-CSRFToken": "masked-first" },
    });
    expect(fetch.mock.calls[3][1].headers["X-CSRFToken"]).toBe(
      "masked-rotated",
    );
  });

  it("never sends credentials when CSRF preparation fails", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 403 }));
    vi.stubGlobal("fetch", fetch);
    await expect(api.login("person", "fixture-only")).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1]).not.toHaveProperty("body");
  });

  it("rejects external URLs and safely handles non-JSON authentication failures", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response("Forbidden", { status: 403 }));
    vi.stubGlobal("fetch", fetch);
    await expect(request("https://evil.example/")).rejects.toThrow(
      "Unsupported API path",
    );
    expect(fetch).not.toHaveBeenCalled();
    await expect(api.me()).rejects.toMatchObject({ status: 403 });
  });

  it("renders loading and accessible account navigation without secrets", () => {
    const markup = renderToStaticMarkup(<Account />);
    expect(markup).toContain("Loading your account");
    expect(markup).toContain('aria-live="polite"');
    expect(markup).not.toContain("fixture-only");
  });
});
