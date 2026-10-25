import { defineConfig } from "@playwright/test";

const port = process.env.PORT || "3000";

export default defineConfig({
  testDir: "./tests",
  testMatch: "*.spec.ts",
  workers: 1,
  outputDir: "playwright-results",
  use: { baseURL: `http://localhost:${port}`, channel: "chrome" },
  webServer: {
    command: `npm run start -- --port ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
  },
});
