import { test, expect } from "@playwright/test";
import fs from "node:fs";

const fixture = JSON.parse(
  fs.readFileSync("/tmp/ppi-browser-journey.json", "utf8"),
);
const navigation = (page) =>
  page.getByRole("navigation", {
    name: "Organization navigation",
    exact: true,
  });
const sections = [
  ["Overview", "dashboard", "Overview"],
  ["Products", "products", "Products with a traceable history."],
  ["Imports and review", "imports", "Evidence imports"],
  ["Equipment and rules", "equipment", "Equipment profiles"],
  ["Assessments", "assessments", "Compatibility assessments"],
  ["Plan and usage", "commercial", "Plan and usage"],
  ["Billing history", "billing", "Billing history"],
  ["Integrations", "integrations", "Integrations"],
  ["Organization settings", "settings", "Organization settings"],
];

function textContrast(foreground, background) {
  const luminance = (color) => {
    const rgb = color
      .match(/[\d.]+/g)
      .slice(0, 3)
      .map(Number);
    return rgb
      .map((value) => {
        const channel = value / 255;
        return channel <= 0.04045
          ? channel / 12.92
          : ((channel + 0.055) / 1.055) ** 2.4;
      })
      .reduce(
        (sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index],
        0,
      );
  };
  const values = [luminance(foreground), luminance(background)].sort(
    (a, b) => b - a,
  );
  return (values[0] + 0.05) / (values[1] + 0.05);
}

async function login(page, credentials) {
  await page.goto("/account");
  await page.getByLabel("Username", { exact: true }).fill(credentials.username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByLabel("Active organization", { exact: true }),
  ).toBeVisible();
}

// Supporting fixture setup/denial probes use ordinary session + CSRF APIs.
// Customer navigation, product creation/editing and logout use rendered controls.
async function authorized(page, path, method = "GET", data) {
  return page.evaluate(
    async ({ path, method, data }) => {
      const headers = { "Content-Type": "application/json" };
      if (method !== "GET") {
        const csrf = await (await fetch("/api/v1/auth/csrf/")).json();
        headers["X-CSRFToken"] = csrf.csrfToken;
      }
      const response = await fetch(path, {
        method,
        headers,
        body: data === undefined ? undefined : JSON.stringify(data),
      });
      const text = await response.text();
      return { status: response.status, data: text ? JSON.parse(text) : null };
    },
    { path, method, data },
  );
}

async function createOrganization(page, code, suffix) {
  await page.goto("/account");
  const name = `Dashboard synthetic ${code}-${suffix}`;
  await page.getByLabel("Organization name", { exact: true }).fill(name);
  await page
    .getByLabel("Unique slug", { exact: true })
    .fill(`dashboard-${code}-${suffix}`);
  const response = page.waitForResponse(
    (result) =>
      result.request().method() === "POST" &&
      new URL(result.url()).pathname === "/api/v1/organizations/",
  );
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  const created = await response;
  expect(created.status()).toBe(201);
  return { ...(await created.json()), name };
}

async function selectOrganization(page, organization) {
  const chooser = page.getByLabel("Active organization", { exact: true });
  await expect(chooser).toBeVisible();
  await expect(chooser).toBeEnabled();
  for (let index = 0; index < 50; index++) {
    if (await chooser.locator(`option[value="${organization}"]`).count()) break;
    const loaded = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname === "/api/v1/auth/memberships/",
    );
    await page
      .getByRole("button", { name: "Load more organizations", exact: true })
      .click();
    const result = await (await loaded).json();
    if (result.results.length)
      await expect(
        chooser.locator(`option[value="${result.results[0].organization.id}"]`),
      ).toHaveCount(1);
    await expect(chooser).toBeEnabled();
  }
  await chooser.selectOption(organization);
  await expect(page).toHaveURL(
    new RegExp(`/organizations/${organization}/dashboard$`),
  );
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
}

async function checkSections(page, organization, expected = sections) {
  for (const [label, path, heading] of expected) {
    const link = navigation(page).getByRole("link", {
      name: label,
      exact: true,
    });
    await link.click();
    await expect(page).toHaveURL(
      new RegExp(`/organizations/${organization}/${path}$`),
    );
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    await expect(link).toHaveAttribute("aria-current", "page");
    await expect(navigation(page)).toHaveCount(1);
    await expect(
      page.getByLabel("Active organization", { exact: true }),
    ).toHaveValue(organization);
    await expect(page.getByRole("main")).toHaveCount(1);
  }
}

test("unified dashboard organization, roles, routes and mobile keyboard journey", async ({
  page,
  browser,
}) => {
  test.setTimeout(300000);
  const suffix = Date.now().toString(36);
  const observed = { browser: browser.version(), steps: [] };
  const runtimeErrors = [];
  const hydrationErrors = [];
  const intentionalFaults = new Set();
  const network = {
    browser_injected_faults: [],
    expected_access_denials: [],
    unexpected_server_errors: [],
  };
  function observeNetwork(surface) {
    surface.on("response", (response) => {
      const path = new URL(response.url()).pathname;
      if (!path.startsWith("/api/v1/") || response.status() < 400) return;
      const row = { path, status: response.status() };
      if (intentionalFaults.has(path))
        network.browser_injected_faults.push(row);
      else if (response.status() >= 500)
        network.unexpected_server_errors.push(row);
      else if ([401, 403, 404].includes(response.status()))
        network.expected_access_denials.push(row);
    });
  }
  observeNetwork(page);
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      /hydration|hydrating|react error/i.test(message.text())
    )
      hydrationErrors.push(message.text());
  });
  const mark = (checkpoint) => {
    observed.steps.push(checkpoint);
    console.log(JSON.stringify({ dashboard_checkpoint: checkpoint }));
  };
  await page.setViewportSize({ width: 1440, height: 960 });
  await login(page, fixture.owner);
  const first = await createOrganization(page, "a", suffix);
  const second = await createOrganization(page, "b", suffix);
  await page.goto("/account");
  await selectOrganization(page, first.id);
  await checkSections(page, first.id);
  mark("chooser_canonical_dashboard_owner_nine_sections_single_workspace");

  const root = `/organizations/${first.id}`;
  const api = `/api/v1/organizations/${first.id}/`;
  await page.goto(root + "/products/new");
  const productName = "Dashboard carton " + suffix;
  await page
    .getByLabel("Organization SKU", { exact: true })
    .fill("DASH-" + suffix);
  await page.getByLabel("Product name", { exact: true }).fill(productName);
  await page
    .getByRole("button", { name: "Create product", exact: true })
    .click();
  await expect(page).toHaveURL(/\/products\/[0-9a-f-]+$/);
  const productURL = page.url();
  const product = new URL(productURL).pathname.split("/").pop();
  await page.getByRole("link", { name: "Edit product", exact: true }).click();
  await page
    .getByLabel("Product name", { exact: true })
    .fill(productName + " revised");
  await page
    .getByLabel("Reason for this revision", { exact: true })
    .fill("Synthetic dashboard revision");
  await page
    .getByRole("button", { name: "Save product changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: productName + " revised", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: productName + " revised", exact: true }),
  ).toBeVisible();
  await navigation(page)
    .getByRole("link", { name: "Products", exact: true })
    .click();
  await expect(page).toHaveURL(root + "/products");
  await page.goBack();
  await expect(page).toHaveURL(productURL);
  await page.goForward();
  await expect(page).toHaveURL(root + "/products");
  mark("product_create_edit_direct_refresh_back_forward_preserved");

  const archived = await authorized(page, api + "products/", "POST", {
    sku: "ARCHIVE-" + suffix,
    revision: {
      name: "Archived synthetic carton",
      change_reason: "Synthetic archive count fixture",
    },
  });
  expect(archived.status).toBe(201);
  expect(
    (
      await authorized(
        page,
        api + `products/${archived.data.id}/state/`,
        "POST",
        { is_active: false },
      )
    ).status,
  ).toBe(200);
  const allProducts = await authorized(page, api + "products/?status=all");
  const summary = await authorized(page, api + "dashboard/");
  expect(summary.status).toBe(200);
  expect(summary.data.products).toEqual({
    total: allProducts.data.count,
    active: 1,
    archived: 1,
  });
  expect(summary.data.organization.id).toBe(first.id);
  expect(summary.data.scope).toBe("all_time");
  await page.goto(root + "/dashboard");
  await expect(
    page.getByRole("heading", { name: "Products", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("2 total products", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("1 active · 1 archived", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("0 total imports, all statuses", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("0 assessments, all time", { exact: true }),
  ).toBeVisible();
  mark("real_all_time_aggregate_matches_scoped_active_archived_catalog");

  const optionalPaths = [`**${api}commercial/`, `**${api}integrations/`];
  intentionalFaults.add(api + "commercial/");
  intentionalFaults.add(api + "integrations/");
  for (const path of optionalPaths) {
    await page.route(path, (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Synthetic optional summary failure" }),
      }),
    );
  }
  await page.reload();
  await expect(
    page.getByText("2 total products", { exact: true }),
  ).toBeVisible();
  for (const title of ["Plan and usage", "Integration deliveries"]) {
    const region = page.getByRole("region", { name: title, exact: true });
    await expect(region.getByRole("alert")).toContainText("Unavailable:");
  }
  for (const path of optionalPaths) await page.unroute(path);
  intentionalFaults.delete(api + "commercial/");
  intentionalFaults.delete(api + "integrations/");
  for (const title of ["Plan and usage", "Integration deliveries"]) {
    const region = page.getByRole("region", { name: title, exact: true });
    await region
      .getByRole("button", {
        name: `Retry ${title.toLowerCase()}`,
        exact: true,
      })
      .click();
    await expect(
      region.getByRole("button", {
        name: `Refresh ${title.toLowerCase()}`,
        exact: true,
      }),
    ).toBeVisible();
  }
  mark(
    "browser_injected_optional_errors_leave_core_available_independent_retry",
  );

  // Synthetic browser fault: the backend remains healthy and the retry is real.
  let injected = false;
  const dashboardPath = `**${api}dashboard/`;
  intentionalFaults.add(api + "dashboard/");
  await page.route(dashboardPath, async (route) => {
    if (!injected) {
      injected = true;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Synthetic transient dashboard failure",
        }),
      });
    } else await route.continue();
  });
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Overview unavailable", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Retry overview", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Refresh overview", exact: true }),
  ).toBeVisible();
  await page.unroute(dashboardPath);
  intentionalFaults.delete(api + "dashboard/");
  mark("browser_injected_transient_error_explicit_retry_real_backend");

  // Hold an actual authorized response while selecting a different tenant.
  let releaseResponse;
  let reportHeld;
  const responseHeld = new Promise((resolve) => {
    reportHeld = resolve;
  });
  const releaseGate = new Promise((resolve) => {
    releaseResponse = resolve;
  });
  await page.route(dashboardPath, async (route) => {
    const response = await route.fetch();
    reportHeld();
    await releaseGate;
    try {
      await route.fulfill({ response });
    } catch {
      // An aborted request is also a successful stale-response protection.
    }
  });
  await page
    .getByRole("button", { name: "Refresh overview", exact: true })
    .click();
  await responseHeld;
  await expect(
    page.getByText("Loading organization overview…", { exact: true }),
  ).toBeVisible();
  try {
    await selectOrganization(page, second.id);
  } finally {
    releaseResponse();
  }
  await page.unroute(dashboardPath);
  await expect(
    page.getByLabel("Active organization", { exact: true }),
  ).toHaveValue(second.id);
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("0 total products", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: productName + " revised", exact: true }),
  ).toHaveCount(0);
  expect(
    (await authorized(page, `/api/v1/organizations/${second.id}/dashboard/`))
      .data.products.total,
  ).toBe(0);
  mark(
    "inflight_first_organization_response_does_not_replace_second_workspace",
  );

  for (const width of [820, 390]) {
    await page.setViewportSize({ width, height: 844 });
    const open = page.getByRole("button", {
      name: "Open navigation",
      exact: true,
    });
    await expect(open).toBeVisible();
    await open.click();
    const close = page.getByRole("button", {
      name: "Close navigation",
      exact: true,
    });
    await expect(close).toBeVisible();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const focusable = dialog.locator(
      'a[href],button:not([disabled]),select:not([disabled]),[tabindex="0"]',
    );
    await focusable.last().focus();
    await page.keyboard.press("Tab");
    await expect(focusable.first()).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(close).toBeHidden();
    await expect(open).toBeFocused();
    await open.click();
    await navigation(page)
      .getByRole("link", { name: "Products", exact: true })
      .click();
    await expect(close).toBeHidden();
    await expect(page).toHaveURL(`/organizations/${second.id}/products`);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    const colors = await page
      .locator("a.button-link")
      .filter({ hasText: "Create product" })
      .evaluate((element) => {
        const style = window.getComputedStyle(element);
        return { foreground: style.color, background: style.backgroundColor };
      });
    expect(
      textContrast(colors.foreground, colors.background),
    ).toBeGreaterThanOrEqual(4.5);
    if (width === 390)
      await page.screenshot({
        path: "/results/dashboard-mobile.png",
        fullPage: true,
      });
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await selectOrganization(page, first.id);
  await expect(
    page
      .getByRole("region", { name: "Plan and usage", exact: true })
      .getByRole("button", { name: "Refresh plan and usage", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Integration deliveries", exact: true })
      .getByRole("button", {
        name: "Refresh integration deliveries",
        exact: true,
      }),
  ).toBeVisible();
  await page.screenshot({
    path: "/results/dashboard-desktop.png",
    fullPage: true,
  });
  mark(
    "tablet_phone_drawer_keyboard_focus_escape_link_dismissal_no_page_overflow",
  );

  const membership = await authorized(page, api + "members/", "POST", {
    username: fixture.outsider.username,
    role: "admin",
  });
  expect(membership.status).toBe(201);
  const outsiderContext = await browser.newContext({
    baseURL: "https://edge:8443",
    ignoreHTTPSErrors: false,
  });
  const outsider = await outsiderContext.newPage();
  observeNetwork(outsider);
  outsider.on("pageerror", (error) => runtimeErrors.push(error.message));
  outsider.on("console", (message) => {
    if (
      message.type() === "error" &&
      /hydration|hydrating|react error/i.test(message.text())
    )
      hydrationErrors.push(message.text());
  });
  try {
    await login(outsider, fixture.outsider);
    await outsider.goto(root + "/dashboard");
    await checkSections(outsider, first.id);
    mark("administrator_nine_sections_with_authoritative_permissions");
    expect(
      (
        await authorized(
          page,
          api + `members/${membership.data.id}/`,
          "PATCH",
          { role: "member" },
        )
      ).status,
    ).toBe(200);
    await outsider.goto(root + "/dashboard");
    for (const name of ["Plan and usage", "Billing history", "Integrations"])
      await expect(
        navigation(outsider).getByRole("link", { name, exact: true }),
      ).toHaveCount(0);
    await checkSections(
      outsider,
      first.id,
      sections.filter(
        ([, path]) => !["commercial", "billing", "integrations"].includes(path),
      ),
    );
    for (const path of ["commercial", "billing", "integrations"]) {
      await outsider.goto(root + "/" + path);
      await expect(
        outsider
          .getByRole("alert")
          .filter({ hasText: /owners and administrators/ }),
      ).toContainText(/owners and administrators/);
      expect((await authorized(outsider, api + path + "/")).status).toBe(403);
    }
    await outsider.goto(`/organizations/${second.id}/dashboard`);
    await expect(
      outsider
        .getByRole("alert")
        .filter({ hasText: /Organization access is unavailable/ }),
    ).toContainText(/Organization access is unavailable/);
    expect(
      (
        await authorized(
          outsider,
          `/api/v1/organizations/${second.id}/dashboard/`,
        )
      ).status,
    ).toBe(404);
    expect(
      (await authorized(page, api + `members/${membership.data.id}/`, "DELETE"))
        .status,
    ).toBe(204);
    await outsider.goto(root + "/products/" + product);
    await expect(
      outsider
        .getByRole("alert")
        .filter({ hasText: /Organization access is unavailable/ }),
    ).toContainText(/Organization access is unavailable/);
    expect((await authorized(outsider, api + "dashboard/")).status).toBe(404);
    mark(
      "member_hidden_restricted_sections_direct_denials_foreign_and_revoked_access",
    );
  } finally {
    await outsiderContext.close();
  }
  await page.goto(root + "/dashboard");
  await page.locator('header a[href="/account"]').click();
  await expect(page).toHaveURL(/\/account$/);
  await selectOrganization(page, first.id);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  expect((await authorized(page, api + "dashboard/")).status).toBe(403);
  await page.goto("/account/recover");
  await expect(
    page.getByRole("heading", { name: "Account recovery", exact: true }),
  ).toBeVisible();
  expect(runtimeErrors).toEqual([]);
  expect(hydrationErrors).toEqual([]);
  expect(network.unexpected_server_errors).toEqual([]);
  mark("header_account_logout_recovery_no_runtime_or_hydration_errors");
  fs.writeFileSync(
    "/results/dashboard-acceptance.json",
    JSON.stringify(
      {
        ...observed,
        status: "passed",
        organizations: [first.id, second.id],
        product,
        console: {
          runtime_errors: runtimeErrors.length,
          hydration_errors: hydrationErrors.length,
        },
        network,
      },
      null,
      2,
    ),
  );
});
