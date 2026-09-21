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
 * The backend is fully mocked via page.route(), so no FastAPI server is required.
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
  test("UX-03: simple choice triggers PATCH choice → POST recontrol → success announcement", async ({
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

    let review = reviewWith(anomaly);
    await setupBaselineMocks(mockedApi, review);

    let recontrolCalled = false;

    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      const body = route.request().postDataJSON();
      expect(body).toMatchObject({
        action: "choice",
        outcome: "correct_and_recontrol",
      });
      review = reviewWith({ ...anomaly, uxChoice: "correct_and_recontrol", status: "Ouverte" });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(review),
      });
    });

    await mockedApi.route(
      new RegExp(`/orders/anomalies/${anomaly.anomalyId}/recontrol$`),
      async (route) => {
        recontrolCalled = true;
        review = reviewWith({ ...anomaly, uxChoice: "correct_and_recontrol", status: "Corrigée" });
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(review),
        });
      },
    );

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    await expect(
      page.getByRole("button", { name: "J'ai renseigné le numéro de commande" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "J'ai renseigné le numéro de commande" }).click();

    await expect
      .poll(() => recontrolCalled, { timeout: 5_000 })
      .toBe(true);

    const patchCalls = mockedApi
      .calls()
      .filter(
        (c) =>
          c.method === "PATCH" &&
          c.url.includes(`/orders/anomalies/${anomaly.anomalyId}`) &&
          !c.url.endsWith("/recontrol"),
      );
    expect(patchCalls).toHaveLength(1);
    expect(patchCalls[0].body).toMatchObject({
      action: "choice",
      outcome: "correct_and_recontrol",
    });
  });

  test("UX-13: 'nouvelle commande' choice prompts for justification and forwards it", async ({
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
        body: JSON.stringify(reviewWith({ ...anomaly, uxChoice: "confirm_new_order_and_recontrol" })),
      });
    });

    await mockedApi.route(
      new RegExp(`/orders/anomalies/${anomaly.anomalyId}/recontrol$`),
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(reviewWith(anomaly)),
        });
      },
    );

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    // The frontend calls window.prompt for justification-required outcomes.
    page.once("dialog", async (dialog) => {
      expect(dialog.type()).toBe("prompt");
      await dialog.accept("Facture 123 est différente");
    });

    await page.getByRole("button", { name: "J'ai vérifié : c'est une nouvelle commande" }).click();

    await expect.poll(() => patchBody).not.toBeNull();
    expect(patchBody).toMatchObject({
      action: "choice",
      outcome: "confirm_new_order_and_recontrol",
      justification: "Facture 123 est différente",
    });
  });

  test("UX-13: empty justification aborts the request (no PATCH sent)", async ({
    page,
    mockedApi,
  }) => {
    const anomaly = mockAnomaly({
      anomalyId: "an-dup-empty",
      uxId: "UX-13",
      uxChoices: CHOICES_PO_DUPLICATE,
    });

    await setupBaselineMocks(mockedApi, reviewWith(anomaly));

    let patchCalled = false;
    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      patchCalled = true;
      await route.abort();
    });

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    page.once("dialog", async (dialog) => {
      await dialog.accept("   "); // whitespace only → treated as empty
    });

    await page.getByRole("button", { name: "J'ai vérifié : c'est une nouvelle commande" }).click();

    // Give the app a moment to (not) fire the request
    await page.waitForTimeout(500);
    expect(patchCalled).toBe(false);
  });

  test("UX-16: 'correct_and_regenerate' chains PATCH → generateEdifact → recontrol", async ({
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

    const events: string[] = [];

    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      events.push("patch");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(reviewWith(anomaly)),
      });
    });

    await mockedApi.route(new RegExp(`/orders/${MOCK_ORDER_ID}/generate-edifact$`), async (route) => {
      events.push("generate");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, edifact: "UNB+..." }),
      });
    });

    await mockedApi.route(
      new RegExp(`/orders/anomalies/${anomaly.anomalyId}/recontrol$`),
      async (route) => {
        events.push("recontrol");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(reviewWith(anomaly)),
        });
      },
    );

    await page.goto(`/revue/${MOCK_ORDER_ID}`);

    await page.getByRole("button", { name: "J'ai corrigé les informations de la commande" }).click();

    await expect.poll(() => events).toEqual(["patch", "generate", "recontrol"]);
  });

  test("UX-16: generateEdifact failure surfaces an error dialog and stops the chain", async ({
    page,
    mockedApi,
  }) => {
    const anomaly = mockAnomaly({
      anomalyId: "an-edi-fail",
      message: "EDIFACT_MISSING_BGM",
      issueDomain: "EDI",
      uxId: "UX-16",
      uxChoices: CHOICES_EDI_MISSING,
    });

    await setupBaselineMocks(mockedApi, reviewWith(anomaly));

    let recontrolCalled = false;
    await mockedApi.route(new RegExp(`/orders/anomalies/${anomaly.anomalyId}$`), async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(reviewWith(anomaly)),
      });
    });
    await mockedApi.route(new RegExp(`/orders/${MOCK_ORDER_ID}/generate-edifact$`), async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: false, errors: ["Segment BGM manquant"] }),
      });
    });
    await mockedApi.route(
      new RegExp(`/orders/anomalies/${anomaly.anomalyId}/recontrol$`),
      async (route) => {
        recontrolCalled = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(reviewWith(anomaly)),
        });
      },
    );

    await page.goto(`/revue/${MOCK_ORDER_ID}`);
    await page.getByRole("button", { name: "J'ai corrigé les informations de la commande" }).click();

    await expect(page.getByText(/Choix non enregistré/i)).toBeVisible();
    await expect(page.getByText(/Segment BGM manquant/i)).toBeVisible();
    expect(recontrolCalled).toBe(false);
  });
});
