import { test as base, expect, type Page, type Route } from "@playwright/test";

/**
 * Shared E2E fixtures for File2EDI.
 *
 * `mockedApi` provides a helper to intercept /api/** requests. Each spec registers
 * the routes it needs — no global state, no shared session between tests.
 */

export interface MockedApi {
  /** Register a handler for a specific API path (relative to /api). */
  route(path: string | RegExp, handler: (route: Route) => Promise<void> | void): Promise<void>;
  /** Convenience: respond with JSON body and 200 status. */
  json(path: string | RegExp, body: unknown, status?: number): Promise<void>;
  /** Track calls captured for a route (by url + method), returned in call order. */
  calls(): Array<{ url: string; method: string; body: unknown }>;
}

type CallRecord = { url: string; method: string; body: unknown };

function buildMatcher(path: string | RegExp): RegExp {
  if (path instanceof RegExp) return path;
  const escaped = path.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
  return new RegExp(`(^|/)api${escaped}(\\?|$)`);
}

async function attachMockedApi(page: Page): Promise<{ api: MockedApi; calls: CallRecord[] }> {
  const calls: CallRecord[] = [];

  const api: MockedApi = {
    async route(path, handler) {
      const matcher = buildMatcher(path);
      await page.route(matcher, async (route) => {
        const req = route.request();
        calls.push({
          url: req.url(),
          method: req.method(),
          body: req.postDataJSON() ?? null,
        });
        await handler(route);
      });
    },
    async json(path, body, status = 200) {
      await api.route(path, async (route) => {
        await route.fulfill({
          status,
          contentType: "application/json",
          body: JSON.stringify(body),
        });
      });
    },
    calls() {
      return [...calls];
    },
  };

  return { api, calls };
}

export const test = base.extend<{ mockedApi: MockedApi }>({
  mockedApi: async ({ page }, use) => {
    const { api } = await attachMockedApi(page);
    await use(api);
  },
});

export { expect };
