import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Home from "../app/page";
import { GET } from "../app/health/route";

describe("foundation contract", () => {
  it("identifies the platform and clearly discloses unavailable workflows", () => {
    const html = renderToStaticMarkup(<Home />);
    expect(html).toContain("Physical Product Intelligence Cloud");
    expect(html).toContain(
      "Product ingestion and assessment workflows are not yet available.",
    );
    expect(html).toContain('aria-labelledby="title"');
    expect(html).not.toContain("<form");
  });

  it("returns a non-cacheable frontend-only health response", async () => {
    const response = GET();
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.json()).toEqual({
      status: "ok",
      service: "frontend",
    });
  });
});
