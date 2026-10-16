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
  await page.getByLabel("Active organization").selectOption(org);
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
  // Existing API-only membership management is setup, never a substitute for the UI workflows.
  const membership = await authorized(page, api + "members/", "POST", {
    username: fixture.outsider.username,
    role: "member",
  });
  expect(membership.status).toBe(201);
  const outsiderContext = await browser.newContext({
    ignoreHTTPSErrors: false,
    baseURL: "https://edge:8443",
  });
  const outsider = await outsiderContext.newPage();
  await login(outsider, fixture.outsider);
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
  expect(
    (
      await authorized(
        page,
        api + "members/" + membership.data.id + "/",
        "DELETE",
      )
    ).status,
  ).toBe(204);
  await outsider.goto(root + "/products/" + product);
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
  await page.getByLabel("Active organization").selectOption(second);
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
