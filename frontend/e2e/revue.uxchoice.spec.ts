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
 * These specs exercise the UX-01..UX-20 choice flow introduced by src/ux_catalog.py.
 *
 * The current RevuePage.onChoose handler (commit 6b0c572) is minimalist: it fires a
 * single `PATCH /orders/anomalies/{id}` with action=choice + outcome, then relies on
 * react-query to invalidate the order review. Any richer orchestration (justification
 * prompts, generate/SFTP chaining, recontrol side-calls) is intentionally handled by
 * the backend based on the outcome — the frontend just posts the choice and reacts.
 *
 * These specs pin THAT contract. If the frontend grows back a client-side chain, the
 * tests will fail on the extra network calls and we'll know to update them explicitly.
 */

const CHOICES_ORDER_KEY_MISSING: OrderAnomaly["uxChoices"] = [
  { label: "J'ai renseigné le numéro de commande", outcome: "correct_and_recontrol" },
  {
    label: "J'ai vérifié : l'information n'est pas présente sur le document",
    outcome: "keep_blocked",
  },
];

const CHOICES_PO_DUPLICATE: OrderAnomaly["uxChoices"] = [
  {
    label: "J'ai vérifié : c'est une nouvelle commande",
    outcome: "confirm_new_order_and_recontrol",
  },
  {
    label: "J'ai vérifié : cette commande existe déjà dans SAP",
    outcome: "keep_blocked",
  },
];

const CHOICES_EDI_MISSING: OrderAnomaly["uxChoices"] = [
  { label: "J'ai corrigé les informations de la commande", outcome: "correct_and_regenerate" },
  { label: "J'ai vérifié : les informations sont correctes", outcome: "regenerate_and_recontrol" },
  { label: "Je n'ai pas pu corriger les informations", outcome: "keep_blocked" },
];

function reviewWith(anomaly: OrderAnomaly): OrderReview {
  return mockOrderReview({ anomalies: [anomaly] });
}

async function setupBaselineMocks(mockedApi: import("./fixtures").MockedApi, review: OrderReview) {
  await mockedApi.json(/\/auth\/modes$/, { modes: ["profile"], require_auth: true });
  await mockedApi.json(/\/me$/, mockCurrentUser());
  await mockedApi.json(/\/health\/system$/, mockSystemHealth());
  await mockedApi.json(/\/users$/, []);
  await mockedApi.json(/\/settings$/, {});
  await mockedApi.json(new RegExp(`/orders/${MOCK_ORDER_ID}/review$`), review);
}

test.describe("Revue — UX choice flow", () => {
  test("UX-03: click on a choice fires PATCH action=choice with the outcome", async ({
    page,
    mockedApi,
  }) => {
    const anomaly = mockAnomaly({
      anomalyId: "an-order-key",
      message: "ORDER_KEY_MISSING",
      uxId: "UX-03",
      uxGroup: "Commande",
      uxMessage: "Génie n'a pas pu identifier le numéro de commande d'achat",
      uxChoices: CHOICES_ORDER_KEY_MISSING,
      requiresRecontrol: true,
    });

    await setupBaselineMocks(mockedApi, reviewWith(anomaly));

    let patchBody: unknown = null;
    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      patchBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(reviewWith({ ...anomaly, uxChoice: "correct_and_recontrol" })),
      });
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);
    await expect(
      page.getByRole("button", { name: "J'ai renseigné le numéro de commande" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "J'ai renseigné le numéro de commande" }).click();

    await expect.poll(() => patchBody, { timeout: 5_000 }).not.toBeNull();
    expect(patchBody).toMatchObject({
      action: "choice",
      outcome: "correct_and_recontrol",
    });
  });

  test("UX-13: 'nouvelle commande' choice posts confirm_new_order_and_recontrol", async ({
    page,
    mockedApi,
  }) => {
    const anomaly = mockAnomaly({
      anomalyId: "an-dup",
      message: "PO_NUMBER_DUPLICATE",
      issueDomain: "DUPLICATE",
      uxId: "UX-13",
      uxChoices: CHOICES_PO_DUPLICATE,
      requiresRecontrol: true,
    });

    await setupBaselineMocks(mockedApi, reviewWith(anomaly));

    let patchBody: unknown = null;
    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      patchBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(reviewWith(anomaly)),
      });
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);
    await page.getByRole("button", { name: "J'ai vérifié : c'est une nouvelle commande" }).click();

    await expect.poll(() => patchBody, { timeout: 5_000 }).not.toBeNull();
    expect(patchBody).toMatchObject({
      action: "choice",
      outcome: "confirm_new_order_and_recontrol",
    });
  });

  test("UX-16: EDI regenerate choice posts correct_and_regenerate", async ({
    page,
    mockedApi,
  }) => {
    const anomaly = mockAnomaly({
      anomalyId: "an-edi",
      message: "EDIFACT_MISSING_BGM",
      issueDomain: "EDI",
      uxId: "UX-16",
      uxChoices: CHOICES_EDI_MISSING,
      requiresRecontrol: true,
    });

    await setupBaselineMocks(mockedApi, reviewWith(anomaly));

    let patchBody: unknown = null;
    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      patchBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(reviewWith(anomaly)),
      });
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);
    await page.getByRole("button", { name: "J'ai corrigé les informations de la commande" }).click();

    await expect.poll(() => patchBody, { timeout: 5_000 }).not.toBeNull();
    expect(patchBody).toMatchObject({
      action: "choice",
      outcome: "correct_and_regenerate",
    });
  });

  test("PATCH failure surfaces an error dialog and preserves the anomaly", async ({
    page,
    mockedApi,
  }) => {
    const anomaly = mockAnomaly({
      anomalyId: "an-fail",
      message: "ORDER_KEY_MISSING",
      uxId: "UX-03",
      uxChoices: CHOICES_ORDER_KEY_MISSING,
    });

    await setupBaselineMocks(mockedApi, reviewWith(anomaly));

    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Une justification est obligatoire pour ce choix" }),
      });
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);
    await page.getByRole("button", { name: "J'ai renseigné le numéro de commande" }).click();

    await expect(page.getByText(/Choix non enregistré/i)).toBeVisible();
    await expect(page.getByText(/justification est obligatoire/i)).toBeVisible();
  });

  test("choices are disabled while the workflow is locked", async ({ page, mockedApi }) => {
    const anomaly = mockAnomaly({
      anomalyId: "an-locked",
      uxId: "UX-03",
      uxChoices: CHOICES_ORDER_KEY_MISSING,
    });
    // The workflow lock trigger is `isSentToSap` (order.status === "Envoyé SAP" or sapSentAt set)
    // — that's the state where AnomaliesTable receives disabled=true.
    const lockedReview: OrderReview = mockOrderReview({
      anomalies: [anomaly],
      order: { ...mockOrderReview().order, status: "Envoyé SAP", sapSentAt: "2026-09-21T12:00:00Z" },
    });
    await setupBaselineMocks(mockedApi, lockedReview);

    await page.goto(`/revue/${MOCK_ORDER_ID}`);
    const btn = page.getByRole("button", { name: "J'ai renseigné le numéro de commande" });
    await expect(btn).toBeVisible();
    await expect(btn).toBeDisabled();
  });
});
