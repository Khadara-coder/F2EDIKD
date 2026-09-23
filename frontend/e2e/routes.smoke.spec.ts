import { expect, test } from "@playwright/test";

/**
 * Smoke suite against the real backend. Direct replacement of scripts/browser_smoke.mjs.
 *
 * Prerequisites:
 *   - Backend reachable at F2EDI_BASE_URL (default http://127.0.0.1:8000)
 *   - F2EDI_USER + F2EDI_PASSWORD env vars set → auth.setup.ts logs in and saves the session
 *
 * Without credentials, only the guest login-page check runs; the authenticated tests are skipped.
 */

const HAS_CREDENTIALS = Boolean(process.env.F2EDI_USER && process.env.F2EDI_PASSWORD);

const ROUTES: { path: string; expect: RegExp }[] = [
  { path: "/", expect: /Cockpit/i },
  { path: "/convertir", expect: /Convertir|Importer|PDF/i },
  { path: "/revue", expect: /Revue|commande/i },
  { path: "/historique", expect: /Historique/i },
  { path: "/donnees-maitres", expect: /Données maîtres/i },
  { path: "/parametres", expect: /Paramètres/i },
];

test.describe("Smoke — guest", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("login page renders", async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/login`, { waitUntil: "networkidle" });
    const body = page.locator("body");
    await expect(body).toContainText(/Identifiant/i);
    await expect(body).toContainText(/Mot de passe/i);
    await expect(page.getByRole("button", { name: /Se connecter/i })).toBeVisible();
  });
});

test.describe("Smoke — authenticated routes", () => {
  test.skip(!HAS_CREDENTIALS, "F2EDI_USER / F2EDI_PASSWORD not set");

  for (const route of ROUTES) {
    test(`${route.path} loads and matches expected content`, async ({ page, baseURL }) => {
      const response = await page.goto(`${baseURL}${route.path}`, { waitUntil: "networkidle" });
      expect(response?.status(), `HTTP ${response?.status()} on ${route.path}`).toBeLessThan(400);

      const body = page.locator("body");
      await expect(body, `${route.path} shows a session error`).not.toContainText(
        /Impossible de charger la session/i,
      );
      await expect(body, `${route.path} missing expected content`).toContainText(route.expect);
    });
  }
});

test.describe("Smoke — mobile sidebar", () => {
  test.skip(!HAS_CREDENTIALS, "F2EDI_USER / F2EDI_PASSWORD not set");

  // Only run this on the mobile-smoke project (iPhone 13 viewport).
  test.skip(({ viewport }) => (viewport?.width ?? 0) >= 900, "mobile-only");

  test("hamburger opens and closes the sidebar overlay", async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/`, { waitUntil: "networkidle" });

    const menuBtn = page.getByRole("button", { name: "Ouvrir le menu" });
    await expect(menuBtn).toBeVisible();
    await menuBtn.click();

    const closeBtn = page.getByRole("button", { name: "Fermer le menu" });
    await expect(closeBtn).toBeVisible();
    await closeBtn.click();

    // Sidebar closed → hamburger is visible again (more reliable than asserting
    // closeBtn is hidden, since the sidebar may unmount rather than just hide).
    await expect(menuBtn).toBeVisible();
  });
});
