import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "../app/api/v1/[...path]/route";

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("same-origin API transport", () => {
  it("forwards a bounded integration bearer only on dedicated read routes", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ results: [] }));
    vi.stubGlobal("fetch", fetch);
    const token = "Bearer ppi_i_" + "a".repeat(32) + "." + "b".repeat(43);
    await GET(
      new Request("http://localhost:3000/api/v1/integration/products/", {
        headers: { Authorization: token },
      }),
      context(["integration", "products"]),
    );
    expect(fetch.mock.calls[0][1].headers.get("authorization")).toBe(token);
    await POST(
      new Request("http://localhost:3000/api/v1/integration/products/", {
        method: "POST",
        headers: { Authorization: token },
      }),
      context(["integration", "products"]),
    );
    expect(fetch.mock.calls[1][1].headers.has("authorization")).toBe(false);
  });
  it("forwards cookies, CSRF and origin only to the fixed backend with canonical slashes", async () => {
    vi.stubEnv("API_BACKEND_ORIGIN", "http://backend:8000");
    const fetch = vi
      .fn()
      .mockResolvedValue(Response.json({ detail: "Denied" }, { status: 403 }));
    vi.stubGlobal("fetch", fetch);
    const response = await POST(
      new Request("http://localhost:3000/api/v1/organizations/?page=2", {
        method: "POST",
        body: JSON.stringify({ name: "Example", slug: "example" }),
        headers: {
          Cookie: "sessionid=fixture-only",
          "X-CSRFToken": "masked-fixture",
          Origin: "http://localhost:3000",
          "Content-Type": "application/json",
          "X-Forwarded-Proto": "https",
          Authorization: "fixture-not-forwarded",
        },
      }),
      context(["organizations"]),
    );
    expect(String(fetch.mock.calls[0][0])).toBe(
      "http://backend:8000/api/v1/organizations/?page=2",
    );
    const options = fetch.mock.calls[0][1];
    expect(options.headers.get("cookie")).toBe("sessionid=fixture-only");
    expect(options.headers.get("x-csrftoken")).toBe("masked-fixture");
    expect(options.headers.get("origin")).toBe("http://localhost:3000");
    expect(options.headers.has("x-forwarded-proto")).toBe(false);
    expect(options.headers.has("authorization")).toBe(false);
    expect(options).toMatchObject({ cache: "no-store", redirect: "manual" });
    expect(response.status).toBe(403);
    expect(response.headers.get("cache-control")).toContain("no-store");
  });

  it("preserves both rotated cookies and omits decompression-sensitive headers", async () => {
    const headers = new Headers({
      "Content-Encoding": "gzip",
      "Content-Length": "999",
    });
    headers.append("Set-Cookie", "sessionid=fixture; HttpOnly; SameSite=Lax");
    headers.append("Set-Cookie", "csrftoken=fixture; SameSite=Lax");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ id: 1 }, { headers })),
    );
    const response = await GET(
      new Request("http://localhost:3000/api/v1/auth/me/"),
      context(["auth", "me"]),
    );
    expect(response.headers.getSetCookie()).toHaveLength(2);
    expect(response.headers.has("content-encoding")).toBe(false);
    expect(response.headers.has("content-length")).toBe(false);
    expect(await response.json()).toEqual({ id: 1 });
  });

  it("preserves a bodyless logout response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    const response = await POST(
      new Request("http://localhost:3000/api/v1/auth/logout/", {
        method: "POST",
      }),
      context(["auth", "logout"]),
    );
    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
  });

  it("rejects oversized streamed bodies before sending credentials upstream", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const response = await POST(
      new Request("http://localhost:3000/api/v1/auth/register/", {
        method: "POST",
        body: "x".repeat(65_537),
      }),
      context(["auth", "register"]),
    );
    expect(response.status).toBe(413);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("blocks traversal before making any backend request", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    expect(
      (
        await GET(
          new Request("http://localhost:3000/api/v1/auth/me/"),
          context(["..", "admin"]),
        )
      ).status,
    ).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("fails safely without replaying a mutation or logging secrets", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("fixture-private-error"));
    vi.stubGlobal("fetch", fetch);
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const response = await POST(
      new Request("http://localhost:3000/api/v1/auth/login/", {
        method: "POST",
        body: "{}",
      }),
      context(["auth", "login"]),
    );
    expect(response.status).toBe(502);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(log.mock.calls.flat().join(" ")).not.toContain(
      "fixture-private-error",
    );
    expect(await response.json()).toEqual({ detail: "Backend unavailable." });
  });
});
