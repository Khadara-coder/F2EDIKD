/**
 * Browser smoke tests for File2EDI (responsive + key routes).
 *
 * Usage:
 *   $env:F2EDI_USER = "khadara"
 *   $env:F2EDI_PASSWORD = "<your-dev-password>"
 *   node scripts/browser_smoke.mjs
 */
import { chromium, devices } from "playwright";

const BASE = process.env.F2EDI_BASE_URL || "http://127.0.0.1:8000";
const USER = process.env.F2EDI_USER || "";
const PASSWORD = process.env.F2EDI_PASSWORD || "";

const routes = [
  { path: "/", expect: /Cockpit/i },
  { path: "/convertir", expect: /Convertir|Importer|PDF/i },
  { path: "/revue", expect: /Revue|commande/i },
  { path: "/historique", expect: /Historique/i },
  { path: "/donnees-maitres", expect: /Données maîtres/i },
  { path: "/parametres", expect: /Paramètres/i },
];

function fail(msg) {
  console.error(`[FAIL] ${msg}`);
  process.exitCode = 1;
}

function ok(msg) {
  console.log(`[OK] ${msg}`);
}

async function assertRoute(page, { path, expect: pattern }) {
  const res = await page.goto(`${BASE}${path}`, { waitUntil: "networkidle", timeout: 30000 });
  const status = res?.status() ?? 0;
  if (status >= 400) {
    fail(`${path} HTTP ${status}`);
    return false;
  }
  const body = await page.locator("body").innerText();
  if (/Impossible de charger la session/i.test(body)) {
    fail(`${path} session error`);
    return false;
  }
  if (!pattern.test(body)) {
    fail(`${path} missing expected content (${pattern})`);
    return false;
  }
  ok(`${path} loaded`);
  return true;
}

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle", timeout: 30000 });
  await page.getByPlaceholder("Votre identifiant").fill(USER);
  await page.getByPlaceholder("Mot de passe").fill(PASSWORD);
  await page.getByRole("button", { name: /Se connecter/i }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15000 });
  const body = await page.locator("body").innerText();
  if (/Identifiant ou mot de passe incorrect/i.test(body)) {
    throw new Error("invalid credentials");
  }
  ok("login succeeded");
}

async function testLoginPage(page, label) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle", timeout: 30000 });
  const body = await page.locator("body").innerText();
  if (!/File2EDI/i.test(body) || !/Identifiant/i.test(body)) {
    fail(`${label}: login page missing expected fields`);
    return false;
  }
  ok(`${label}: login page renders`);
  return true;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  let failed = 0;

  // Guest: login page desktop + mobile
  const guestDesktop = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  if (!(await testLoginPage(await guestDesktop.newPage(), "desktop"))) failed += 1;
  await guestDesktop.close();

  const guestMobile = await browser.newContext({ ...devices["iPhone 13"] });
  const guestMobilePage = await guestMobile.newPage();
  if (!(await testLoginPage(guestMobilePage, "mobile"))) failed += 1;
  await guestMobile.close();

  if (!USER || !PASSWORD) {
    console.log("[SKIP] authenticated routes (set F2EDI_USER and F2EDI_PASSWORD)");
    await browser.close();
    if (failed > 0) process.exit(1);
    ok("guest browser smoke checks passed");
    return;
  }

  // Desktop authenticated
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const desktopPage = await desktop.newPage();
  try {
    await login(desktopPage);
    for (const route of routes) {
      if (!(await assertRoute(desktopPage, route))) failed += 1;
    }
  } catch (err) {
    fail(`desktop login: ${err.message}`);
    failed += 1;
  }
  await desktop.close();

  // Mobile authenticated + sidebar
  const mobile = await browser.newContext({ ...devices["iPhone 13"] });
  const mobilePage = await mobile.newPage();
  try {
    await login(mobilePage);
    await mobilePage.goto(`${BASE}/`, { waitUntil: "networkidle", timeout: 30000 });
    const menuBtn = mobilePage.getByRole("button", { name: "Ouvrir le menu" });
    if (!(await menuBtn.isVisible())) {
      fail("mobile: hamburger menu not visible");
      failed += 1;
    } else {
      await menuBtn.click();
      const closeBtn = mobilePage.getByRole("button", { name: "Fermer le menu" });
      if (!(await closeBtn.isVisible())) {
        fail("mobile: sidebar overlay did not open");
        failed += 1;
      } else {
        ok("mobile sidebar opens");
        await closeBtn.click();
      }
    }
    if (!(await assertRoute(mobilePage, { path: "/revue", expect: /Revue|commande/i }))) {
      failed += 1;
    }
  } catch (err) {
    fail(`mobile login: ${err.message}`);
    failed += 1;
  }
  await mobile.close();
  await browser.close();

  if (failed > 0) {
    fail(`${failed} browser check(s) failed`);
    process.exit(1);
  }
  ok("all browser smoke checks passed");
}

main().catch((err) => {
  console.error("[FAIL]", err);
  process.exit(1);
});
