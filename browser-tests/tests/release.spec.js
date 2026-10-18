import { test, expect } from "@playwright/test";
import fs from "node:fs";
const fixture = JSON.parse(
  fs.readFileSync("/tmp/ppi-browser-journey.json", "utf8"),
);
const suffix = Date.now().toString(36);
const form = (page, name) => page.getByRole("form", { name, exact: true });
const submit = async (page, name) =>
  form(page, name).getByRole("button", { name, exact: true }).click();
async function login(page, credentials) {
  await page.goto("/account");
  await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
  await page.getByLabel("Username", { exact: true }).fill(credentials.username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Active organization")).toBeVisible();
}
// Supporting authorization probes use the real signed-in browser and normal CSRF endpoint.
// Main catalog/import/review/rule/assessment mutations below use the rendered forms.
async function authorized(page, path, method = "GET", data) {
  return page.evaluate(
    async ({ path, method, data }) => {
      const headers = { "Content-Type": "application/json" };
      if (method !== "GET") {
        const csrf = await (await fetch("/api/v1/auth/csrf/")).json();
        headers["X-CSRFToken"] = csrf.csrfToken;
      }
      const r = await fetch(path, {
        method,
        headers,
        body: data === undefined ? undefined : JSON.stringify(data),
      });
      const body = await r.text();
      return { status: r.status, data: body ? JSON.parse(body) : null };
    },
    { path, method, data },
  );
}
async function selectOrganization(page, organizationId) {
  for (let pageNumber = 0; pageNumber < 25; pageNumber++) {
    const found = await page
      .getByLabel("Active organization")
      .locator("option")
      .evaluateAll(
        (options, id) => options.some((option) => option.value === id),
        organizationId,
      );
    if (found) break;
    const more = page.getByRole("button", {
      name: "Load more organizations",
      exact: true,
    });
    await expect(more).toBeVisible();
    await more.click();
    await expect(page.getByLabel("Active organization")).toBeEnabled();
  }
  await page.getByLabel("Active organization").selectOption(organizationId);
}
async function createOrg(page, code) {
  await page.goto("/account");
  await page
    .getByLabel("Organization name", { exact: true })
    .fill(`Browser synthetic ${code}-${suffix}`);
  await page.getByLabel("Unique slug").fill(`browser-${code}-${suffix}`);
  const response = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      /\/organizations\/$/.test(new URL(r.url()).pathname),
  );
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  const r = await response;
  expect(r.status()).toBe(201);
  return (await r.json()).id;
}
test("real HTTPS browser release journey with reviewed recorded extraction", async ({
  page,
  browser,
}) => {
  test.setTimeout(300000);
  const observed = {
    browser: browser.version(),
    baseURL: "https://edge:8443",
    steps: [],
  };
  const mark = (value) => {
    observed.steps.push(value);
    console.log(JSON.stringify({ checkpoint: value }));
  };
  await login(page, fixture.owner);
  const cookies = await page.context().cookies();
  const session = cookies.find((c) => c.name === "sessionid");
  expect(session.secure && session.httpOnly && session.sameSite === "Lax").toBe(
    true,
  );
  const org = await createOrg(page, "a"),
    second = await createOrg(page, "b");
  await selectOrganization(page, org);
  await page
    .getByRole("link", { name: "Open product catalog", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Products with a traceable history." }),
  ).toBeVisible();
  mark("login_secure_cookie_organization_selection");
  const root = `/organizations/${org}`,
    api = `/api/v1/organizations/${org}/`;
  const capability = await authorized(page, api + "imports/ai-capabilities/");
  expect(capability.data.reason).toBe("synthetic_rehearsal_only");
  await page.goto(root + "/products/new");
  await page
    .getByLabel("Organization SKU", { exact: true })
    .fill("BROWSER-" + suffix);
  await page
    .getByLabel("Product name", { exact: true })
    .fill("Synthetic browser carton " + suffix);
  await submit(page, "Create product");
  await expect(page).toHaveURL(/\/products\/[0-9a-f-]+$/);
  const productURL = page.url(),
    product = new URL(productURL).pathname.split("/").pop();
  await page.getByText("Add packaging configuration", { exact: true }).click();
  await page
    .getByLabel("Packaging profile name", { exact: true })
    .fill("Synthetic shipping case");
  await page
    .getByRole("combobox", { name: "Packaging level", exact: true })
    .selectOption("case");
  await submit(page, "Create packaging profile");
  await expect(
    page.getByRole("heading", { name: "Synthetic shipping case", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Synthetic shipping case", exact: true }),
  ).toBeVisible();
  mark("product_packaging_persistence");
  await page.goto(root + "/imports");
  await page.getByLabel("Source file").setInputFiles({
    name: "unsupported.exe",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("Synthetic unsupported format"),
  });
  const rejectedUpload = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      new URL(r.url()).pathname === api + "imports/",
  );
  await submit(page, "Upload source");
  expect((await rejectedUpload).status()).toBe(400);
  await expect(form(page, "Upload source").getByRole("alert")).toBeVisible();
  await page.getByLabel("Source file").setInputFiles({
    name: "synthetic.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "sku,name,notes\nBROWSER-" + suffix + ",Fixture,Weight: 1200 g\n",
    ),
  });
  const acceptedUpload = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      new URL(r.url()).pathname === api + "imports/",
  );
  await submit(page, "Upload source");
  const uploadReceipt = await acceptedUpload;
  expect(
    uploadReceipt.status(),
    uploadReceipt.status() === 201
      ? ""
      : (await uploadReceipt.text()).slice(0, 1500),
  ).toBe(201);
  await expect(page).toHaveURL(/\/imports\/[0-9a-f-]+$/);
  const source = new URL(page.url()).pathname.split("/").pop();
  await expect(page.getByText(/Scan: clean/)).toBeVisible();
  const receivedSource = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "Download private source", exact: true })
    .click();
  const downloadedSource = await (await receivedSource).path();
  expect(fs.readFileSync(downloadedSource)).toEqual(
    Buffer.from(
      "sku,name,notes\nBROWSER-" + suffix + ",Fixture,Weight: 1200 g\n",
    ),
  );
  mark("authorized_private_download_byte_integrity");
  await page.getByLabel("Target SKU or name").fill("BROWSER-" + suffix);
  await submit(page, "Search extraction targets");
  await page
    .getByRole("button", { name: new RegExp("BROWSER-" + suffix) })
    .click();
  await submit(page, "Queue extraction for selected target");
  await expect(
    page.getByRole("heading", { name: "AI extraction processing" }),
  ).toBeVisible();
  await expect(page.getByText(/Provider recorded/)).toBeVisible();
  await submit(page, "Run AI extraction — sends source text");
  await expect(
    page.getByRole("heading", { name: "Review candidate attributes" }),
  ).toBeVisible();
  await expect(page.locator("blockquote")).toHaveText("Weight: 1200 g");
  await page.getByLabel(/Explicitly select this reported measurement/).check();
  await page
    .getByLabel("Review / conflict resolution reason")
    .fill("Human checked synthetic Weight: 1200 g source");
  await submit(page, "Save candidate decision");
  await expect(page.getByText(/Reviewed by actor/)).toBeVisible();
  await submit(page, "Apply approved changes");
  await expect(
    page.getByRole("heading", { name: "Import status: completed" }),
  ).toBeVisible();
  const job = new URL(page.url()).pathname.split("/").pop();
  mark(
    "real_scanned_upload_recorded_proposal_human_review_canonical_selection",
  );
  await page.goto(productURL);
  for (const [attribute, value] of [
    ["length", "10"],
    ["width", "20"],
    ["height", "30"],
  ]) {
    const f = form(page, "Record attribute claim");
    await f
      .getByRole("combobox", { name: "Attribute", exact: true })
      .selectOption(attribute);
    await f.getByLabel("Value", { exact: true }).fill(value);
    await f
      .getByRole("combobox", { name: "Declared unit", exact: true })
      .selectOption("mm");
    await f
      .getByLabel("Source title", { exact: true })
      .fill("Synthetic dimension specification");
    await f
      .getByLabel("Source or notebook reference")
      .fill("Synthetic browser fixture dimensions");
    await f
      .getByLabel("Observer / attribution")
      .fill("Synthetic acceptance operator");
    await f
      .getByLabel("License or rights declaration", { exact: false })
      .fill("Synthetic test data");
    await f
      .getByLabel("Observed at (your local time)")
      .fill(new Date().toISOString().slice(0, 16));
    await submit(page, "Record attribute claim");
    await expect(f.getByLabel("Value", { exact: true })).toHaveValue("");
  }
  await page.goto(root + "/equipment");
  await page.getByLabel("Stable equipment code").fill("BROWSER-" + suffix);
  await page
    .getByLabel("Equipment name", { exact: true })
    .fill("Synthetic browser handling " + suffix);
  await form(page, "Create equipment draft")
    .getByRole("combobox", { name: "Category", exact: true })
    .selectOption("handling");
  await form(page, "Create equipment draft")
    .getByLabel("unit", { exact: true })
    .check();
  await page
    .getByLabel("Manufacturer document or specification reference")
    .fill("Synthetic test specification");
  await page
    .getByLabel("Operational context / intended workflow")
    .fill("Synthetic static carton handling acceptance");
  await submit(page, "Create equipment draft");
  await expect(page).toHaveURL(/\/equipment\/[0-9a-f-]+$/);
  const equipmentURL = page.url(),
    equipment = new URL(equipmentURL).pathname.split("/").pop();
  async function saveRule(limit, version) {
    const f = form(page, "Save rule-set draft");
    await f
      .getByLabel("Rule-set name", { exact: true })
      .fill("Synthetic mass envelope " + version);
    await f
      .getByLabel("Input evidence policy")
      .selectOption("reported_or_measured");
    for (const [i, attribute] of [
      "length",
      "width",
      "height",
      "mass",
    ].entries()) {
      const rule = f.locator(".rule-editor").nth(i);
      await rule
        .getByRole("combobox", { name: "Attribute", exact: true })
        .selectOption(attribute);
      await rule
        .getByLabel("Rule name", { exact: true })
        .fill("Synthetic maximum " + attribute);
      await rule
        .getByLabel("Documented limit")
        .fill(attribute === "mass" ? limit : "1000");
      await rule
        .getByLabel("Explicit rule unit")
        .selectOption(attribute === "mass" ? "kg" : "mm");
      await rule
        .getByLabel("Rule explanation")
        .fill("Synthetic documented maximum; no safety certification");
      await rule
        .getByLabel("Specification provenance reference")
        .fill("Synthetic browser fixture");
    }
    await f
      .getByLabel("Rule-set change reason")
      .fill("Synthetic acceptance version " + version);
    await submit(page, "Save rule-set draft");
    const activate = form(page, `Activate rule-set ${version}`);
    await activate
      .getByLabel("Activation review reason")
      .fill("Human reviewed synthetic specification");
    const activation = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        /\/activate\/$/.test(new URL(r.url()).pathname),
    );
    await submit(page, `Activate rule-set ${version}`);
    const activated = await activation;
    expect(activated.status(), (await activated.text()).slice(0, 1500)).toBe(
      200,
    );
  }
  await saveRule("2", 1);
  async function assess(expected) {
    await page.goto(root + "/assessments");
    await page.getByLabel("Product SKU or name").fill("BROWSER-" + suffix);
    await submit(page, "Search products for assessment");
    await page
      .getByRole("group", { name: "Product selection", exact: true })
      .getByRole("button", { name: new RegExp("BROWSER-" + suffix) })
      .click();
    await page.getByLabel("Equipment code or name").fill("BROWSER-" + suffix);
    await submit(page, "Search equipment for assessment");
    await page
      .getByRole("group", { name: "Active equipment selection", exact: true })
      .getByRole("button", { name: new RegExp("BROWSER-" + suffix) })
      .click();
    await page
      .getByLabel("Eligible activated rule-set version")
      .selectOption({ index: 1 });
    await page
      .getByLabel("Product-level handling context", { exact: false })
      .selectOption("unit");
    await page
      .getByRole("combobox", { name: "Explicit orientation", exact: true })
      .selectOption("as_recorded");
    await submit(page, "Run compatibility assessment");
    await expect(
      page.getByRole("heading", {
        name: "Assessment: " + expected,
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Per-rule explanations" }),
    ).toBeVisible();
    return page.url();
  }
  const compatible = await assess("compatible");
  const frozenAssessment = (
    await authorized(
      page,
      api +
        "assessments/" +
        new URL(compatible).pathname.split("/").pop() +
        "/",
    )
  ).data;
  await page.goto(productURL);
  const conflict = form(page, "Record attribute claim");
  await conflict.getByLabel("Value", { exact: true }).fill("1.4");
  await conflict
    .getByRole("combobox", { name: "Declared unit", exact: true })
    .selectOption("kg");
  await conflict
    .getByLabel("Source title", { exact: true })
    .fill("Synthetic competing specification");
  await conflict
    .getByLabel("Source or notebook reference")
    .fill("Synthetic conflicting mass");
  await conflict
    .getByLabel("Observer / attribution")
    .fill("Synthetic acceptance operator");
  await conflict
    .getByLabel("License or rights declaration", { exact: false })
    .fill("Synthetic test data");
  await conflict
    .getByLabel("Observed at (your local time)")
    .fill(new Date().toISOString().slice(0, 16));
  await submit(page, "Record attribute claim");
  await expect(conflict.getByLabel("Value", { exact: true })).toHaveValue("");
  await assess("indeterminate");
  mark("competing_claims_cannot_become_compatible");
  await page.goto(equipmentURL);
  await page
    .getByRole("button", { name: "Use version 1 as next draft", exact: true })
    .click();
  await saveRule("0.5", 2);
  await assess("incompatible");
  await page.goto(compatible);
  await expect(
    page.getByRole("heading", { name: "Assessment: compatible", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Historical snapshot" }),
  ).toBeVisible();
  expect(
    (
      await authorized(
        page,
        api +
          "assessments/" +
          new URL(compatible).pathname.split("/").pop() +
          "/",
      )
    ).data,
  ).toEqual(frozenAssessment);
  await page.screenshot({
    path: "/results/compatible-history.png",
    fullPage: true,
  });
  mark("equipment_rules_compatible_incompatible_immutable_history");
  // A newly created product with no mass must remain indeterminate under the same rule.
  await page.goto(root + "/products/new");
  await page
    .getByLabel("Organization SKU", { exact: true })
    .fill("UNKNOWN-" + suffix);
  await page
    .getByLabel("Product name", { exact: true })
    .fill("Synthetic missing evidence");
  await submit(page, "Create product");
  await expect(page).toHaveURL(/\/products\/[0-9a-f-]+$/);
  await page.goto(root + "/assessments");
  await page.getByLabel("Product SKU or name").fill("UNKNOWN-" + suffix);
  await submit(page, "Search products for assessment");
  await page
    .getByRole("button", { name: new RegExp("UNKNOWN-" + suffix) })
    .click();
  await page.getByLabel("Equipment code or name").fill("BROWSER-" + suffix);
  await submit(page, "Search equipment for assessment");
  await page
    .getByRole("group", { name: "Active equipment selection", exact: true })
    .getByRole("button", { name: new RegExp("BROWSER-" + suffix) })
    .click();
  await page
    .getByLabel("Eligible activated rule-set version")
    .selectOption({ index: 1 });
  await page
    .getByLabel("Product-level handling context", { exact: false })
    .selectOption("unit");
  await page
    .getByRole("combobox", { name: "Explicit orientation", exact: true })
    .selectOption("as_recorded");
  await submit(page, "Run compatibility assessment");
  await expect(
    page.getByRole("heading", {
      name: "Assessment: indeterminate",
      exact: true,
    }),
  ).toBeVisible();
  mark("missing_evidence_indeterminate");
  await page.getByRole("link", { name: "Plan and usage", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Plan and usage", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Manual pilot · version 1", { exact: true }),
  ).toBeVisible();
  const usageReceipt = await authorized(page, api + "commercial/");
  expect(usageReceipt.status).toBe(200);
  expect(usageReceipt.data.meters.assessments.used).toBe(4);
  expect(usageReceipt.data.meters.extractions.used).toBe(1);
  await expect(page.getByRole("table")).toContainText("Unlimited");
  if (fixture.commercial) {
    for (const status of ["exhausted", "suspended", "expired"]) {
      await page.goto(
        `/organizations/${fixture.commercial[status]}/commercial`,
      );
      await expect(
        page.getByRole("heading", { name: "Plan and usage", exact: true }),
      ).toBeVisible();
      if (status === "exhausted") {
        await expect(page.getByRole("table")).toContainText(
          "Allowance exhausted",
        );
        await page.goto(
          `/organizations/${fixture.commercial[status]}/products/new`,
        );
        await page
          .getByLabel("Organization SKU", { exact: true })
          .fill("DENIED-CAP");
        await page
          .getByLabel("Product name", { exact: true })
          .fill("Denied by capacity");
        await submit(page, "Create product");
        await expect(
          form(page, "Create product").getByRole("alert"),
        ).toContainText("Active product limit reached");
      } else {
        await expect(page.getByText(status, { exact: true })).toBeVisible();
      }
    }
    await page.goto(root + "/commercial");
    await expect(
      page.getByText("Manual pilot · version 1", { exact: true }),
    ).toBeVisible();
  }
  mark("commercial_owner_usage_switching_finite_expired_suspended");
  await page.goto(root + "/billing");
  await expect(
    page.getByRole("heading", { name: "Billing history", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No statements yet.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Pay now", exact: true }),
  ).toHaveCount(0);
  if (fixture.billing) {
    const pending = fixture.billing.pending;
    await page.goto(`/organizations/${pending.org}/billing`);
    await expect(
      page.getByRole("heading", { name: "Billing history", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("pending", { exact: true })).toBeVisible();
    fs.writeFileSync(
      "/results/billing-confirmation-request.json",
      JSON.stringify({ requested: true }),
    );
    await expect
      .poll(
        async () => {
          await page
            .getByRole("button", {
              name: "Refresh billing history",
              exact: true,
            })
            .click();
          return (
            await authorized(
              page,
              `/api/v1/organizations/${pending.org}/billing/`,
            )
          ).data.statements[0].settlement_status;
        },
        { timeout: 90000, intervals: [1000, 3000] },
      )
      .toBe("settled");
    await page
      .getByRole("button", { name: "Refresh billing history", exact: true })
      .click();
    await expect(page.getByText("settled", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Access assignment: Recorded", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: "/results/billing-settled.png",
      fullPage: true,
    });
    const downloaded = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "Download internal statement", exact: true })
      .click();
    expect(fs.readFileSync(await (await downloaded).path(), "utf8")).toContain(
      "not a tax invoice",
    );
    for (const state of ["partial", "unknown", "action_required"]) {
      await page.goto(`/organizations/${fixture.billing[state].org}/billing`);
      await expect(
        page.getByRole("heading", { name: "Billing history", exact: true }),
      ).toBeVisible();
      if (state === "partial")
        await expect(
          page.getByText("partially settled", { exact: true }),
        ).toBeVisible();
      else if (state === "unknown")
        await expect(
          page.getByText(/do not start a duplicate request/),
        ).toBeVisible();
      else
        await expect(
          page.getByText("action required", { exact: true }),
        ).toBeVisible();
    }
    await page.goto(root + "/billing");
    await expect(
      page.getByText("No statements yet.", { exact: true }),
    ).toBeVisible();
  }
  mark("billing_delayed_verified_confirmation_history_download_switching");
  if (fixture.integrations) {
    const integrationRoot = `/organizations/${fixture.integrations.organization_id}/integrations`;
    await page.goto(integrationRoot);
    await expect(
      page.getByRole("heading", { name: "Integrations", exact: true }),
    ).toBeVisible();
    const credentials = form(page, "Credential form");
    await credentials
      .getByLabel("Name", { exact: true })
      .fill("Warehouse reader");
    await credentials
      .getByRole("button", { name: "Create credential", exact: true })
      .click();
    await expect(
      page.getByLabel("One-time secret", { exact: true }),
    ).toBeVisible();
    // Never print, snapshot, screenshot or persist the transient secret.
    await page
      .getByRole("button", { name: "I have saved the secret", exact: true })
      .click();
    await expect(
      page.getByLabel("One-time secret", { exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Rotate Warehouse reader", exact: true })
      .click();
    await credentials
      .getByRole("button", { name: "Rotate credential", exact: true })
      .click();
    await expect(
      page.getByLabel("One-time secret", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "I have saved the secret", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Revoke Warehouse reader", exact: true })
      .click();
    await expect(
      page.getByRole("button", {
        name: "Revoke Warehouse reader",
        exact: true,
      }),
    ).toHaveCount(0);
    const destination = form(page, "Destination form");
    await destination
      .getByLabel("HTTPS destination", { exact: true })
      .fill("https://warehouse.example/events");
    await destination
      .getByRole("button", { name: "Add destination", exact: true })
      .click();
    await expect(
      page.getByLabel("One-time secret", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "I have saved the secret", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Rotate signing secret", exact: true })
      .click();
    await expect(
      page.getByLabel("One-time secret", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "I have saved the secret", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Disable destination", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Disable destination", exact: true }),
    ).toBeDisabled();
    await page
      .getByRole("button", { name: "Refresh integrations", exact: true })
      .click();
    await expect(
      page.getByText("Disabled · revision 2 · signing version 2", {
        exact: true,
      }),
    ).toBeVisible();
    await page.screenshot({
      path: "/results/integrations-management.png",
      fullPage: true,
    });
    await page.goto(root + "/integrations");
    await expect(
      page.getByText("No API credentials yet.", { exact: true }),
    ).toBeVisible();
    mark(
      "integration_reveal_once_rotation_revocation_destination_disable_switching",
    );
  }
  await page.goto(root + "/settings");
  await expect(
    page.getByRole("heading", { name: "Organization settings", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Registered username", { exact: true })
    .fill(fixture.outsider.username);
  await page.getByLabel("Initial role", { exact: true }).selectOption("admin");
  await page
    .getByRole("button", { name: "Add organization member", exact: true })
    .click();
  const memberRow = page
    .getByRole("row")
    .filter({ hasText: fixture.outsider.username });
  await expect(memberRow.getByRole("cell").nth(1)).toHaveText("admin");
  await page
    .getByLabel("Role for " + fixture.outsider.username, { exact: true })
    .selectOption("member");
  await page
    .getByRole("button", {
      name: "Save role for " + fixture.outsider.username,
      exact: true,
    })
    .click();
  await expect(memberRow.getByRole("cell").nth(1)).toHaveText("member");
  mark("membership_add_and_role_change_customer_forms");
  const outsiderContext = await browser.newContext({
    ignoreHTTPSErrors: false,
    baseURL: "https://edge:8443",
  });
  const outsider = await outsiderContext.newPage();
  await login(outsider, fixture.outsider);
  if (fixture.billing) {
    await outsider.goto(
      `/organizations/${fixture.billing.partial.org}/billing`,
    );
    await expect(
      outsider.getByRole("heading", { name: "Billing history", exact: true }),
    ).toBeVisible();
    await expect(
      outsider.getByText("partially settled", { exact: true }),
    ).toBeVisible();
  }
  await outsider.goto(root + "/billing");
  if (fixture.integrations) {
    await outsider.goto(
      `/organizations/${fixture.integrations.organization_id}/integrations`,
    );
    await expect(
      outsider.getByRole("heading", { name: "Integrations", exact: true }),
    ).toBeVisible();
    await expect(
      outsider.getByText("No API credentials yet.", { exact: true }),
    ).toHaveCount(0);
    const adminCredentialForm = form(outsider, "Credential form");
    await adminCredentialForm
      .getByLabel("Name", { exact: true })
      .fill("Admin warehouse reader");
    await adminCredentialForm
      .getByRole("button", { name: "Create credential", exact: true })
      .click();
    await expect(
      outsider.getByLabel("One-time secret", { exact: true }),
    ).toBeVisible();
    await outsider
      .getByRole("button", { name: "I have saved the secret", exact: true })
      .click();
    await outsider
      .getByRole("button", {
        name: "Revoke Admin warehouse reader",
        exact: true,
      })
      .click();
    await expect(
      outsider.getByRole("button", {
        name: "Revoke Admin warehouse reader",
        exact: true,
      }),
    ).toHaveCount(0);
    await outsider.goto(root + "/integrations");
    await expect(
      outsider.getByText(
        "Only organization owners and administrators can manage integrations.",
        { exact: true },
      ),
    ).toBeVisible();
    expect((await authorized(outsider, api + "integrations/")).status).toBe(
      403,
    );
    await outsider.goto(root + "/billing");
  }
  await expect(
    outsider.getByRole("alert").filter({ hasText: "Only organization owners" }),
  ).toContainText("Only organization owners and administrators");
  expect((await authorized(outsider, api + "billing/")).status).toBe(403);
  if (fixture.commercial) {
    await outsider.goto(
      `/organizations/${fixture.commercial.admin}/commercial`,
    );
    await expect(
      outsider.getByRole("heading", { name: "Plan and usage", exact: true }),
    ).toBeVisible();
    await expect(outsider.getByRole("table")).toContainText(
      "Allowance exhausted",
    );
  }
  await outsider.goto(root + "/commercial");
  await expect(
    outsider.getByRole("alert").filter({ hasText: "Only organization owners" }),
  ).toContainText("Only organization owners and administrators");
  expect((await authorized(outsider, api + "commercial/")).status).toBe(403);
  await outsider.goto(root + "/imports/" + job);
  await expect(
    outsider.getByRole("heading", { name: "AI extraction processing" }),
  ).toBeVisible();
  await expect(
    outsider.getByRole("button", {
      name: "Save candidate decision",
      exact: true,
    }),
  ).toHaveCount(0);
  const candidates = await authorized(
    outsider,
    api + "imports/" + job + "/candidates/",
  );
  const candidate = candidates.data.results[0];
  expect(
    (
      await authorized(
        outsider,
        api + "imports/" + job + "/candidates/" + candidate.id + "/review/",
        "POST",
        {
          expected_version: candidate.version,
          decision: "approve",
          reason: "Denied member attempt",
        },
      )
    ).status,
  ).toBe(403);
  await outsider.goto(`/organizations/${second}/products/${product}`);
  await expect(
    outsider
      .getByRole("alert")
      .filter({ hasText: "Organization access is unavailable" }),
  ).toBeVisible();
  expect(
    (
      await authorized(
        outsider,
        `/api/v1/organizations/${second}/imports/${source}/file/`,
      )
    ).status,
  ).toBe(404);
  await page.goto(root + "/settings");
  const removal = page.waitForResponse(
    (r) =>
      r.request().method() === "DELETE" &&
      new URL(r.url()).pathname.startsWith(api + "members/"),
  );
  await page
    .getByRole("button", {
      name: "Remove " + fixture.outsider.username,
      exact: true,
    })
    .click();
  expect((await removal).status()).toBe(204);
  await expect(
    page.getByRole("row").filter({ hasText: fixture.outsider.username }),
  ).toHaveCount(0);
  await outsider.goto(root + "/products/" + product);
  expect((await authorized(outsider, api + "commercial/")).status).toBe(404);
  expect((await authorized(outsider, api + "billing/")).status).toBe(404);
  expect((await authorized(outsider, api + "integrations/")).status).toBe(404);
  await expect(
    outsider
      .getByRole("alert")
      .filter({ hasText: "Organization access is unavailable" }),
  ).toBeVisible();
  expect(
    (await authorized(outsider, api + "imports/" + source + "/file/")).status,
  ).toBe(404);
  await outsiderContext.close();
  await page.goto("/account");
  await selectOrganization(page, second);
  await page
    .getByRole("link", { name: "Open product catalog", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "No products in this view",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", {
      name: "Synthetic browser carton " + suffix,
      exact: true,
    }),
  ).toHaveCount(0);
  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  expect((await authorized(page, api + "products/")).status).toBe(403);
  mark("switching_member_role_foreign_file_revocation_logout_denials");
  if (fixture.recovery) {
    const recovery = fixture.recovery;
    await page.goto("/account/recover#token=" + recovery.token);
    await expect(
      page.getByLabel("New password", { exact: true }),
    ).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    await page
      .getByLabel("New password", { exact: true })
      .fill(recovery.new_password);
    await page
      .getByLabel("Confirm new password", { exact: true })
      .fill(recovery.new_password);
    await page
      .getByRole("button", { name: "Update password", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("Password updated");
    await login(page, {
      username: recovery.username,
      password: recovery.new_password,
    });
    await page
      .getByLabel("Current password", { exact: true })
      .fill(recovery.new_password);
    await page
      .getByLabel("New password", { exact: true })
      .fill(recovery.changed_password);
    await page
      .getByLabel("Confirm new password", { exact: true })
      .fill(recovery.changed_password);
    await page
      .getByRole("button", { name: "Update password", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Sign in", exact: true }),
    ).toBeVisible();
    await login(page, {
      username: recovery.username,
      password: recovery.changed_password,
    });
    const settingsPath = `/organizations/${recovery.organization_id}/settings`;
    await page.goto(settingsPath);
    await expect(
      page.getByRole("heading", { name: "Organization settings", exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Organization display name", { exact: true })
      .fill("Recovered organization " + suffix);
    await page
      .getByRole("button", { name: "Rename organization", exact: true })
      .click();
    await expect(page.locator(".workspace-context")).toContainText(
      "Recovered organization " + suffix,
    );
    await page
      .getByLabel("Registered username", { exact: true })
      .fill(fixture.outsider.username);
    await page
      .getByRole("button", { name: "Add organization member", exact: true })
      .click();
    await page
      .getByLabel("Confirm new owner " + fixture.outsider.username, {
        exact: true,
      })
      .fill(fixture.outsider.username);
    await page
      .getByRole("button", {
        name: "Transfer ownership to " + fixture.outsider.username,
        exact: true,
      })
      .click();
    await expect(page.locator(".workspace-context")).toContainText(
      "Your role: admin",
    );
    await expect(
      page.getByRole("button", { name: "Suspend organization", exact: true }),
    ).toHaveCount(0);
    const ownerContext = await browser.newContext({
      ignoreHTTPSErrors: false,
      baseURL: "https://edge:8443",
    });
    const newOwner = await ownerContext.newPage();
    await login(newOwner, fixture.outsider);
    await newOwner.goto(settingsPath);
    await newOwner
      .getByLabel("Confirm suspension slug", { exact: true })
      .fill(recovery.organization_slug);
    await newOwner
      .getByRole("button", { name: "Suspend organization", exact: true })
      .click();
    await expect(
      newOwner.getByRole("button", {
        name: "Reactivate organization",
        exact: true,
      }),
    ).toBeVisible();
    expect(
      (
        await authorized(
          page,
          `/api/v1/organizations/${recovery.organization_id}/members/`,
        )
      ).status,
    ).toBe(404);
    await newOwner
      .getByRole("button", { name: "Reactivate organization", exact: true })
      .click();
    await newOwner
      .getByLabel("Confirm new owner " + recovery.username, { exact: true })
      .fill(recovery.username);
    await newOwner
      .getByRole("button", {
        name: "Transfer ownership to " + recovery.username,
        exact: true,
      })
      .click();
    await expect(newOwner.locator(".workspace-context")).toContainText(
      "Your role: admin",
    );
    await ownerContext.close();
    await page.goto(settingsPath);
    await expect(page.locator(".workspace-context")).toContainText(
      "Your role: owner",
    );
    await page
      .getByRole("button", {
        name: "Remove " + fixture.outsider.username,
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: fixture.outsider.username }),
    ).toHaveCount(0);
    mark("organization_rename_transfer_suspend_reactivate_role_boundaries");
    await page.goto("/account");
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    expect(
      (
        await authorized(page, "/api/v1/auth/recover/", "POST", {
          token: recovery.token,
          new_password: recovery.new_password,
        })
      ).status,
    ).toBe(400);
    mark("operator_issued_recovery_password_change_single_use_logout");
  }
  if (fixture.retention) {
    await login(page, fixture.owner);
    const retained = fixture.retention;
    const settingsPath = `/organizations/${retained.organization_id}/settings`;
    const importPath = `/organizations/${retained.organization_id}/imports/${retained.source_id}`;
    const importApi = `/api/v1/organizations/${retained.organization_id}/imports/`;
    await page.goto(settingsPath);
    await expect(page.getByText(/Legal hold: active/)).toBeVisible();
    await page.goto(importPath);
    await page
      .getByLabel("Source removal reason", { exact: true })
      .fill("Synthetic browser cleanup");
    await page
      .getByLabel("I confirm permanent removal of this unused original file.")
      .check();
    await submit(page, "Request unused source removal");
    await expect(
      form(page, "Request unused source removal").getByRole("alert"),
    ).toContainText(/disabled|legal hold/);
    await page.goto(settingsPath);
    await page
      .getByLabel("Minimum retention age in days (blank disables removal)", {
        exact: true,
      })
      .fill("1");
    await page
      .getByLabel("Legal hold: preserve all original files", { exact: true })
      .uncheck();
    await page
      .getByLabel("Retention policy change reason", { exact: true })
      .fill("Synthetic unused source policy");
    await submit(page, "Save retention policy");
    await expect(page.getByText(/Legal hold: released/)).toBeVisible();
    await page.goto(importPath);
    await page
      .getByLabel("Source removal reason", { exact: true })
      .fill("Synthetic browser cleanup");
    await page
      .getByLabel("I confirm permanent removal of this unused original file.")
      .check();
    await submit(page, "Request unused source removal");
    await expect(form(page, "Request unused source removal")).toHaveCount(0);
    await expect
      .poll(
        async () => {
          await submit(page, "Refresh source file status");
          return (await authorized(page, importApi + retained.source_id + "/"))
            .data.source_file_state;
        },
        { timeout: 45000 },
      )
      .toBe("removed");
    expect(
      (await authorized(page, importApi + retained.source_id + "/file/"))
        .status,
    ).toBe(409);
    const history = await authorized(
      page,
      importApi + retained.source_id + "/history/",
    );
    expect(
      history.data.results.some((row) => row.action === "retention_removed"),
    ).toBe(true);
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Original source file", exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/^File status: removed\./)).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Download private source", exact: true }),
    ).toHaveCount(0);
    await page.screenshot({
      path: "/results/source-retention.png",
      fullPage: true,
    });
    await page.goto(settingsPath);
    await page
      .getByLabel("Legal hold: preserve all original files", { exact: true })
      .check();
    await page
      .getByLabel("Retention policy change reason", { exact: true })
      .fill("Synthetic final preservation hold");
    await submit(page, "Save retention policy");
    await expect(page.getByText(/Legal hold: active/)).toBeVisible();
    mark("default_legal_hold_explicit_unused_source_removal_preserved_history");
  }
  fs.writeFileSync(
    "/results/acceptance.json",
    JSON.stringify(
      {
        ...observed,
        status: "passed",
        org,
        second,
        product,
        equipment,
        source,
        job,
      },
      null,
      2,
    ),
  );
});
