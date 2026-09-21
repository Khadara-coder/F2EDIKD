import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for File2EDI.
 *
 * Two categories of tests coexist under `e2e/`:
 *   - `*.smoke.spec.ts`: run against a real backend (require F2EDI_USER / F2EDI_PASSWORD
 *     and F2EDI_BASE_URL pointing to a running FastAPI server). Replace the old
 *     scripts/browser_smoke.mjs.
 *   - `*.spec.ts` (non-smoke): mock the backend via `page.route()`. They only need the
 *     Vite preview server (which serves the versioned frontend/dist) — no FastAPI, no PG.
 *
 * The `setup` project logs in once against the real backend and stores the session
 * cookie in e2e/.auth/user.json; smoke projects reuse it via `storageState`.
 */

const MOCK_BASE_URL = "http://127.0.0.1:4173";
const SMOKE_BASE_URL = process.env.F2EDI_BASE_URL ?? "http://127.0.0.1:8000";
const HAS_CREDENTIALS = Boolean(process.env.F2EDI_USER && process.env.F2EDI_PASSWORD);
const AUTH_STATE = "e2e/.auth/user.json";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",

  use: {
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },

  // Serve the versioned frontend/dist via Vite preview for mocked specs.
  // Smoke specs override baseURL to point to the real FastAPI server which serves the same dist.
  webServer: {
    command: "npm run preview -- --port 4173 --strictPort",
    url: MOCK_BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },

  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts$/,
      use: { baseURL: SMOKE_BASE_URL },
    },
    {
      name: "chromium-mocked",
      testMatch: /.*\.spec\.ts$/,
      testIgnore: /.*\.smoke\.spec\.ts$/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 800 },
        baseURL: MOCK_BASE_URL,
      },
    },
    {
      name: "chromium-smoke",
      testMatch: /.*\.smoke\.spec\.ts$/,
      dependencies: HAS_CREDENTIALS ? ["setup"] : [],
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 800 },
        baseURL: SMOKE_BASE_URL,
        storageState: HAS_CREDENTIALS ? AUTH_STATE : undefined,
      },
    },
    {
      name: "mobile-smoke",
      testMatch: /.*\.smoke\.spec\.ts$/,
      dependencies: HAS_CREDENTIALS ? ["setup"] : [],
      use: {
        ...devices["iPhone 13"],
        baseURL: SMOKE_BASE_URL,
        storageState: HAS_CREDENTIALS ? AUTH_STATE : undefined,
      },
    },
  ],
});
