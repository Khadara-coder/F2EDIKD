import { expect, test } from "./fixtures";
import {
  MOCK_ORDER_ID,
  mockAnomaly,
  mockCurrentUser,
  mockOrderReview,
  mockSystemHealth,
} from "./fixtures.data";
import type { OrderAnomaly, OrderReview } from "../src/types";

/**
 * Matrix-style E2E coverage of the Revue page's choice UI. Exercises button
 * dispatch, disabled states, keyboard access, and the multi-anomaly
 * independence property directly in the browser — complements the pure-DOM
 * Vitest matrix in AnomaliesTable.matrix.test.tsx.
 */

async function setupBaseline(mockedApi: import("./fixtures").MockedApi, review: OrderReview) {
  await mockedApi.json(/\/auth\/modes$/, { modes: ["profile"], require_auth: true });
  await mockedApi.json(/\/me$/, mockCurrentUser());
  await mockedApi.json(/\/health\/system$/, mockSystemHealth());
  await mockedApi.json(/\/users$/, []);
  await mockedApi.json(/\/settings$/, {});
  await mockedApi.json(new RegExp(`/orders/${MOCK_ORDER_ID}/review$`), review);
  // Catch-all for recontrol side-calls triggered by *_and_recontrol outcomes:
  // without this, the backend ECONNREFUSED opens an error dialog that blocks
  // subsequent UI interactions in tests that click multiple buttons.
  await mockedApi.json(/\/orders\/anomalies\/[^/]+\/recontrol$/, { status: "ok" });
}

test.describe("Revue — choice matrix E2E", () => {
  test("each button of a 3-choice rule (UX-06 shipto) dispatches its own outcome", async ({
    page,
    mockedApi,
  }) => {
    const anomaly: OrderAnomaly = mockAnomaly({
      anomalyId: "an-ux06",
      message: "SHIPTO_NO_STRONG_MATCH",
      issueDomain: "PARTNER",
      uxId: "UX-06",
      uxChoices: [
        { label: "J'ai corrigé le client livré", outcome: "correct_and_recontrol" },
        { label: "J'ai vérifié : le client livré sélectionné est correct", outcome: "confirm_and_recontrol" },
        { label: "Le client livré n'est pas dans la liste des clients livrés", outcome: "keep_blocked_and_escalate" },
      ],
    });

    await setupBaseline(mockedApi, mockOrderReview({ anomalies: [anomaly] }));

    const captured: string[] = [];
    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      const body = route.request().postDataJSON() as { outcome?: string };
      if (body?.outcome) captured.push(body.outcome);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockOrderReview({ anomalies: [anomaly] })),
      });
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    for (const label of [
      "J'ai corrigé le client livré",
      "J'ai vérifié : le client livré sélectionné est correct",
      "Le client livré n'est pas dans la liste des clients livrés",
    ]) {
      await page.getByRole("button", { name: label }).click();
    }

    await expect.poll(() => captured, { timeout: 5_000 }).toEqual([
      "correct_and_recontrol",
      "confirm_and_recontrol",
      "keep_blocked_and_escalate",
    ]);
  });

  test("multi-anomaly page: clicking one anomaly's choice does not affect the others", async ({
    page,
    mockedApi,
  }) => {
    const a1: OrderAnomaly = mockAnomaly({
      anomalyId: "an-1",
      message: "SOLDTO_NOT_FOUND",
      issueDomain: "PARTNER",
      uxId: "UX-07",
      uxChoices: [
        { label: "J'ai corrigé le Sold-to", outcome: "correct_and_recontrol" },
        { label: "J'ai vérifié : le Sold-to sélectionné est correct", outcome: "confirm_and_recontrol" },
      ],
    });
    const a2: OrderAnomaly = mockAnomaly({
      anomalyId: "an-2",
      message: "ORDER_KEY_MISSING",
      issueDomain: "ORDER",
      uxId: "UX-03",
      uxChoices: [
        { label: "J'ai renseigné le numéro de commande", outcome: "correct_and_recontrol" },
        { label: "J'ai vérifié : l'information n'est pas présente sur le document", outcome: "keep_blocked" },
      ],
    });

    await setupBaseline(mockedApi, mockOrderReview({ anomalies: [a1, a2] }));

    const calls: Array<{ anomalyId: string; outcome: string }> = [];
    await mockedApi.route(/\/orders\/anomalies\/(an-1|an-2)$/, async (route) => {
      const url = route.request().url();
      const anomalyId = url.match(/anomalies\/(an-[12])/)?.[1] ?? "unknown";
      const body = route.request().postDataJSON() as { outcome?: string };
      calls.push({ anomalyId, outcome: body?.outcome ?? "" });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockOrderReview({ anomalies: [a1, a2] })),
      });
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    // Click a1's first choice, then a2's second — they should route to their own PATCH.
    await page.getByRole("button", { name: "J'ai corrigé le Sold-to" }).click();
    await page
      .getByRole("button", { name: "J'ai vérifié : l'information n'est pas présente sur le document" })
      .click();

    await expect.poll(() => calls, { timeout: 5_000 }).toEqual([
      { anomalyId: "an-1", outcome: "correct_and_recontrol" },
      { anomalyId: "an-2", outcome: "keep_blocked" },
    ]);
  });

  test("uxChoice highlight is scoped per row (two anomalies, two different pressed buttons)", async ({
    page,
    mockedApi,
  }) => {
    const CHOICES = [
      { label: "Choix A", outcome: "outcome_a" },
      { label: "Choix B", outcome: "outcome_b" },
    ];
    const a1: OrderAnomaly = mockAnomaly({
      anomalyId: "row-1",
      message: "First anomaly",
      issueDomain: "ORDER",
      uxChoices: CHOICES,
      uxChoice: "outcome_a",
    });
    const a2: OrderAnomaly = mockAnomaly({
      anomalyId: "row-2",
      message: "Second anomaly",
      issueDomain: "ORDER",
      uxChoices: CHOICES,
      uxChoice: "outcome_b",
    });

    await setupBaseline(mockedApi, mockOrderReview({ anomalies: [a1, a2] }));

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    const row1 = page.getByRole("row", { name: /First anomaly/i });
    const row2 = page.getByRole("row", { name: /Second anomaly/i });

    // In row1, "Choix A" is pressed (has bg-blue-600), "Choix B" is not.
    await expect(row1.getByRole("button", { name: "Choix A" })).toHaveClass(/bg-blue-600/);
    await expect(row1.getByRole("button", { name: "Choix B" })).not.toHaveClass(/bg-blue-600/);
    // In row2, "Choix B" is pressed, "Choix A" is not.
    await expect(row2.getByRole("button", { name: "Choix A" })).not.toHaveClass(/bg-blue-600/);
    await expect(row2.getByRole("button", { name: "Choix B" })).toHaveClass(/bg-blue-600/);
  });

  test("keyboard: pressing Enter on a focused choice button fires the outcome (row does not intercept)", async ({
    page,
    mockedApi,
  }) => {
    // The row's onKeyDown ignores events targeted at inner interactive
    // elements (`if (e.target !== e.currentTarget) return`), so a focused
    // choice button receives Enter normally and dispatches its click.
    const anomaly = mockAnomaly({
      anomalyId: "kb-target",
      message: "Test keyboard",
      issueDomain: "ORDER",
      uxChoices: [
        { label: "Bouton Enter", outcome: "outcome_enter" },
      ],
    });
    await setupBaseline(mockedApi, mockOrderReview({ anomalies: [anomaly] }));

    let patched = false;
    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      patched = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockOrderReview({ anomalies: [anomaly] })),
      });
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    const btn = page.getByRole("button", { name: "Bouton Enter" });
    await btn.scrollIntoViewIfNeeded();
    await btn.press("Enter");

    await expect.poll(() => patched, { timeout: 5_000 }).toBe(true);

    // The row selection must NOT toggle when the keystroke was directed at
    // an inner interactive element.
    const row = page.getByRole("row", { name: /Test keyboard/i });
    await expect(row).toHaveAttribute("aria-selected", "false");
  });

  test("domain grouping is preserved in the DOM order (Document → Partenaire → Article)", async ({
    page,
    mockedApi,
  }) => {
    // Anomalies intentionally supplied in reverse canonical order.
    const anomalies: OrderAnomaly[] = [
      mockAnomaly({ anomalyId: "art", issueDomain: "ARTICLE", message: "Article anomaly" }),
      mockAnomaly({ anomalyId: "part", issueDomain: "PARTNER", message: "Partner anomaly" }),
      mockAnomaly({ anomalyId: "doc", issueDomain: "DOCUMENT", message: "Document anomaly" }),
    ];
    await setupBaseline(mockedApi, mockOrderReview({ anomalies }));

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    // Wait for the anomalies table to render.
    await expect(page.getByText("Article anomaly")).toBeVisible();

    // Read the DOM order of the three domain header cells.
    const groupCells = await page.locator("td").filter({ hasText: /^(Document|Partenaire|Article)$/ }).allTextContents();
    expect(groupCells).toEqual(["Document", "Partenaire", "Article"]);
  });

  test("clicking on the anomaly message toggles row selection (aria-selected)", async ({
    page,
    mockedApi,
  }) => {
    const anomaly = mockAnomaly({
      anomalyId: "row-select",
      message: "Anomalie sélectionnable",
      issueDomain: "ORDER",
      uxChoices: [{ label: "Choix", outcome: "outcome" }],
    });
    await setupBaseline(mockedApi, mockOrderReview({ anomalies: [anomaly] }));

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    const row = page.getByRole("row", { name: /Anomalie sélectionnable/i });
    await expect(row).toHaveAttribute("aria-selected", "false");

    // Scope the click to the row — selection announces a live-region status
    // that duplicates the message text elsewhere on the page after selection.
    await row.getByText("Anomalie sélectionnable", { exact: true }).click();
    await expect(row).toHaveAttribute("aria-selected", "true");

    // Second click deselects
    await row.getByText("Anomalie sélectionnable", { exact: true }).click();
    await expect(row).toHaveAttribute("aria-selected", "false");
  });

  test("clicking a choice button does NOT toggle row selection", async ({ page, mockedApi }) => {
    const anomaly = mockAnomaly({
      anomalyId: "scope-check",
      message: "Anomalie scope",
      issueDomain: "ORDER",
      uxChoices: [{ label: "Ne toggle pas la row", outcome: "outcome" }],
    });
    await setupBaseline(mockedApi, mockOrderReview({ anomalies: [anomaly] }));

    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockOrderReview({ anomalies: [anomaly] })),
      });
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    const row = page.getByRole("row", { name: /Anomalie scope/i });
    await expect(row).toHaveAttribute("aria-selected", "false");

    await page.getByRole("button", { name: "Ne toggle pas la row" }).click();

    // Selection should stay false — the click on the button must not propagate.
    await expect(row).toHaveAttribute("aria-selected", "false");
  });

  test("severity badges render in French for each level (scoped to the anomalies section)", async ({
    page,
    mockedApi,
  }) => {
    const anomalies: OrderAnomaly[] = [
      mockAnomaly({ anomalyId: "crit", issueSeverity: "CRITICAL", message: "Crit anomaly" }),
      mockAnomaly({ anomalyId: "err", issueSeverity: "ERROR", message: "Err anomaly" }),
      mockAnomaly({ anomalyId: "warn", issueSeverity: "WARNING", message: "Warn anomaly" }),
      mockAnomaly({ anomalyId: "info", issueSeverity: "INFO", message: "Info anomaly" }),
    ];
    await setupBaseline(mockedApi, mockOrderReview({ anomalies }));

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    // Anchor to the anomalies-only region so "Info" doesn't collide with e.g.
    // "Informations générales" elsewhere on the page.
    const section = page.locator("#review-anomalies");
    await expect(section.getByText("Critique", { exact: true })).toBeVisible();
    await expect(section.getByText("Erreur", { exact: true })).toBeVisible();
    await expect(section.getByText("Avertissement", { exact: true })).toBeVisible();
    await expect(section.getByText("Info", { exact: true })).toBeVisible();
  });

  test("empty state renders 'Aucune anomalie.' when the review has no anomalies", async ({
    page,
    mockedApi,
  }) => {
    await setupBaseline(mockedApi, mockOrderReview({ anomalies: [] }));

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    await expect(page.getByText("Aucune anomalie.")).toBeVisible();
    // No choice buttons in the anomalies region.
    await expect(page.locator('#review-anomalies button')).toHaveCount(0);
  });
});
