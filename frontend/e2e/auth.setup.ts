import { expect, test as setup } from "@playwright/test";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";

const AUTH_DIR = "e2e/.auth";
const AUTH_FILE = path.join(AUTH_DIR, "user.json");

setup("authenticate against the real backend", async ({ page, baseURL }) => {
  const user = process.env.F2EDI_USER;
  const password = process.env.F2EDI_PASSWORD;

  if (!user || !password) {
    setup.skip(
      true,
      "F2EDI_USER and F2EDI_PASSWORD must be set to run the smoke suite against the real backend",
    );
    return;
  }

  if (!existsSync(AUTH_DIR)) {
    mkdirSync(AUTH_DIR, { recursive: true });
  }

  await page.goto(`${baseURL}/login`, { waitUntil: "networkidle" });
  await page.getByPlaceholder("Votre identifiant").fill(user);
  await page.getByPlaceholder("Mot de passe").fill(password);
  await page.getByRole("button", { name: /Se connecter/i }).click();

  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15_000 });
  await expect(page.locator("body")).not.toContainText(/Identifiant ou mot de passe incorrect/i);

  await page.context().storageState({ path: AUTH_FILE });
});
