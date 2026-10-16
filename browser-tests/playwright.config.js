import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  retries: 0,
  timeout: 120000,
  expect: { timeout: 15000 },
  reporter: [["line"], ["json", { outputFile: "/results/browser.json" }]],
  outputDir: "/results/run",
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
