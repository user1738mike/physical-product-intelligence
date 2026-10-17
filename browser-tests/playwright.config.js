import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  retries: 0,
  timeout: 180000,
  expect: { timeout: 15000 },
  reporter: [["line"], ["json", { outputFile: "/tmp/ppi-browser.json" }]],
  outputDir: "/tmp/ppi-playwright-output",
  use: {
    actionTimeout: 15000,
    navigationTimeout: 20000,
    baseURL: "https://edge:8443",
    ignoreHTTPSErrors: false,
    launchOptions: { chromiumSandbox: true },
    screenshot: "off",
    trace: "off",
    video: "off",
  },
});
