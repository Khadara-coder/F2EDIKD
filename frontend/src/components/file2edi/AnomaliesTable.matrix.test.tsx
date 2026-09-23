import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { OrderAnomaly } from "@/types";
import { AnomaliesTable } from "./AnomaliesTable";

/**
 * Exhaustive UX-choice matrix tests for AnomaliesTable.
 *
 * The base test file (AnomaliesTable.test.tsx) verifies rendering primitives
 * (empty state, grouping, keyboard nav, severity badges, etc.). This file
 * pins the *matrix* of business rules: every active UX rule in
 * src/ux_catalog.py has an entry here, tested against the button labels the
 * ADV actually sees on the page.
 *
 * Also documents a known data bug (UX-08 has two choices sharing the same
 * outcome value) with a dedicated test so a fix in ux_catalog can be paired
 * with the test flip.
 */

function anomaly(overrides: Partial<OrderAnomaly> = {}): OrderAnomaly {
  return {
    anomalyId: "a-1",
    orderId: "o-1",
    severity: "error",
    message: "Message par défaut",
    status: "Ouverte",
    createdAt: "2026-09-21T10:00:00Z",
    ...overrides,
  };
}

/**
 * The choice matrix mirrors the active UX rules of src/ux_catalog.py exactly.
 * When ux_catalog changes, this table must be updated in lockstep — that is a
 * feature, not a bug. Add a new entry when a new UX-* rule ships.
 */
type UxCase = {
  uxId: string;
  code: string;
  domain: OrderAnomaly["issueDomain"];
  message: string;
  choices: NonNullable<OrderAnomaly["uxChoices"]>;
};

const UX_ACTIVE_MATRIX: UxCase[] = [
  {
    uxId: "UX-01",
    code: "PDF_PARSE_FAILURE",
    domain: "DOCUMENT",
    message: "Génie n'a pas pu confirmer qu'il s'agit d'un bon de commande standard",
    choices: [
      { label: "J'ai pu saisir la commande", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : ce document n'est pas un bon de commande", outcome: "close_without_sap" },
    ],
  },
  {
    uxId: "UX-03",
    code: "ORDER_KEY_MISSING",
    domain: "ORDER",
    message: "Génie n'a pas pu identifier le numéro de commande d'achat",
    choices: [
      { label: "J'ai renseigné le numéro de commande", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : l'information n'est pas présente sur le document", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-04",
    code: "ORDER_DATE_INVALID",
    domain: "ORDER",
    message: "Génie n'a pas pu identifier la date d'émission de la commande",
    choices: [
      { label: "J'ai renseigné la date de commande", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : l'information n'est pas présente sur le document", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-05",
    code: "DELIVERY_DATE_INVALID",
    domain: "ORDER",
    message: "Génie n'a pas pu identifier la date de livraison de la commande",
    choices: [
      { label: "J'ai renseigné la date de livraison de la commande", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : l'information n'est pas présente sur le document", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-06",
    code: "SHIPTO_NO_STRONG_MATCH",
    domain: "PARTNER",
    message: "Génie n'a pas pu identifier le client livré",
    choices: [
      { label: "J'ai corrigé le client livré", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : le client livré sélectionné est correct", outcome: "confirm_and_recontrol" },
      { label: "Le client livré n'est pas dans la liste des clients livrés", outcome: "keep_blocked_and_escalate" },
    ],
  },
  {
    uxId: "UX-07",
    code: "SOLDTO_NOT_FOUND",
    domain: "PARTNER",
    message: "Génie n'a pas pu identifier le sold-to",
    choices: [
      { label: "J'ai corrigé le Sold-to", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : le Sold-to sélectionné est correct", outcome: "confirm_and_recontrol" },
      { label: "Le Sold-to n'est pas dans la liste des Sold-to", outcome: "keep_blocked_and_escalate" },
    ],
  },
  {
    uxId: "UX-09",
    code: "QUANTITY_MISSING",
    domain: "ARTICLE",
    message: "Génie n'a pas pu identifier une quantité valide sur la ligne de commande",
    choices: [
      { label: "J'ai corrigé la quantité", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : la quantité n'est pas présente sur le document", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-10",
    code: "UNIT_PRICE_MISSING",
    domain: "ARTICLE",
    message: "Génie n'a pas pu identifier le prix unitaire sur la ligne de commande",
    choices: [
      { label: "J'ai renseigné le prix unitaire", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : cette commande est acceptée sans prix", outcome: "confirm_no_price_and_recontrol" },
    ],
  },
  {
    uxId: "UX-11",
    code: "NO_LINE_ITEMS",
    domain: "ARTICLE",
    message: "Génie n'a pas pu identifier de ligne de commande exploitable dans le document",
    choices: [
      { label: "J'ai ajouté les lignes de commande", outcome: "correct_and_recontrol" },
      { label: "J'ai vérifié : le document ne contient aucune ligne exploitable", outcome: "keep_blocked_and_escalate" },
    ],
  },
  {
    uxId: "UX-13",
    code: "PO_NUMBER_DUPLICATE",
    domain: "DUPLICATE",
    message: "Génie a identifié un numéro de commande déjà présent dans l'historique SAP",
    choices: [
      { label: "J'ai vérifié : c'est une nouvelle commande", outcome: "confirm_new_order_and_recontrol" },
      { label: "J'ai vérifié : cette commande existe déjà dans SAP", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-14",
    code: "DUPLICATE_ALREADY_SENT",
    domain: "DUPLICATE",
    message: "Génie a identifié que cette commande semble avoir déjà été traitée et envoyée",
    choices: [
      { label: "J'ai vérifié : ce n'est pas la même commande", outcome: "confirm_distinct_order_and_recontrol" },
      { label: "J'ai vérifié : cette commande a déjà été envoyée", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-15",
    code: "MASTERDATA_MISSING",
    domain: "TECHNICAL",
    message: "Génie ne peut pas vérifier la commande car le référentiel SAP est indisponible ou inexploitable",
    choices: [
      { label: "Relancer le contrôle du référentiel", outcome: "retry_masterdata_check" },
      { label: "J'ai signalé le problème au support", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-16",
    code: "EDIFACT_MISSING_BGM",
    domain: "EDI",
    message: "Génie n'a pas pu générer le fichier EDI avec les informations actuelles de la commande",
    choices: [
      { label: "J'ai corrigé les informations de la commande", outcome: "correct_and_regenerate" },
      { label: "J'ai vérifié : les informations sont correctes", outcome: "regenerate_and_recontrol" },
      { label: "Je n'ai pas pu corriger les informations", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-17",
    code: "EDIFACT_LINE_INTEGRITY_MISMATCH",
    domain: "EDI",
    message: "Génie a détecté une incohérence entre la commande et le fichier EDI généré",
    choices: [
      { label: "J'ai corrigé les informations de la commande", outcome: "correct_and_regenerate" },
      { label: "J'ai vérifié : les informations sont correctes", outcome: "regenerate_and_recontrol" },
      { label: "Je n'ai pas pu corriger les informations", outcome: "keep_blocked" },
    ],
  },
  {
    uxId: "UX-18",
    code: "DELIVERY_SFTP_FAILED",
    domain: "DELIVERY",
    message: "Génie n'a pas pu transmettre le fichier EDI vers le destinataire",
    choices: [
      { label: "J'ai relancé l'envoi", outcome: "retry_delivery" },
      { label: "J'ai traité l'envoi manuellement", outcome: "confirm_manual_delivery" },
      { label: "Je n'ai pas pu transmettre la commande", outcome: "keep_blocked" },
    ],
  },
];

describe("AnomaliesTable — UX matrix", () => {
  let onSelect: ReturnType<typeof vi.fn>;
  let onChoose: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onSelect = vi.fn();
    onChoose = vi.fn();
  });

  it.each(UX_ACTIVE_MATRIX)(
    "$uxId ($code): renders every choice button and dispatches its outcome on click",
    async ({ uxId, code, domain, message, choices }) => {
      const user = userEvent.setup();
      render(
        <AnomaliesTable
          anomalies={[
            anomaly({
              anomalyId: `an-${uxId}`,
              message: code,
              uxId,
              uxMessage: message,
              uxChoices: choices,
              issueDomain: domain,
            }),
          ]}
          selectedAnomalyId={null}
          onSelectAnomaly={onSelect}
          onChoose={onChoose}
        />,
      );

      for (const choice of choices) {
        const btn = screen.getByRole("button", { name: choice.label });
        expect(btn).toBeInTheDocument();
        await user.click(btn);
        expect(onChoose).toHaveBeenLastCalledWith(`an-${uxId}`, choice.outcome);
      }

      expect(onChoose).toHaveBeenCalledTimes(choices.length);
    },
  );

  it("UX-08 known data issue: two choices share the same outcome 'correct_and_recontrol'", () => {
    // This test documents a defect in src/ux_catalog.py (UX-08): the first two
    // choices — "J'ai remplacé ou corrigé la référence article" and
    // "J'ai renseigné une référence de remplacement" — both map to
    // "correct_and_recontrol". As long as this duplication exists, selecting
    // one visually highlights BOTH buttons because AnomaliesTable checks
    // `a.uxChoice === choice.outcome` per button. Fix the catalog so each
    // choice carries a distinct outcome, then flip this test to assert the
    // opposite (exactly ONE highlight).
    const CHOICES_UX_08 = [
      { label: "J'ai remplacé ou corrigé la référence article", outcome: "correct_and_recontrol" },
      { label: "J'ai renseigné une référence de remplacement", outcome: "correct_and_recontrol" },
      { label: "J'ai supprimé la ligne concernée", outcome: "delete_line_and_recontrol" },
    ];

    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "an-ux08",
            message: "MATERIAL_STATUS_INVALID",
            uxId: "UX-08",
            uxChoices: CHOICES_UX_08,
            uxChoice: "correct_and_recontrol",
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const first = screen.getByRole("button", { name: "J'ai remplacé ou corrigé la référence article" });
    const second = screen.getByRole("button", { name: "J'ai renseigné une référence de remplacement" });
    const third = screen.getByRole("button", { name: "J'ai supprimé la ligne concernée" });

    // Both share the outcome → both appear "pressed"
    expect(first.className).toContain("bg-blue-600");
    expect(second.className).toContain("bg-blue-600");
    expect(third.className).not.toContain("bg-blue-600");
  });

  it("keeps the highlight scoped to each anomaly's own uxChoice (independent rows)", () => {
    const CHOICES = [
      { label: "Choix A", outcome: "outcome_a" },
      { label: "Choix B", outcome: "outcome_b" },
    ];

    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "a1",
            message: "Anomalie 1",
            uxChoices: CHOICES,
            uxChoice: "outcome_a",
          }),
          anomaly({
            anomalyId: "a2",
            message: "Anomalie 2",
            uxChoices: CHOICES,
            uxChoice: "outcome_b",
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const row1 = screen.getByRole("row", { name: /Anomalie 1/i });
    const row2 = screen.getByRole("row", { name: /Anomalie 2/i });

    const pressed1 = within(row1)
      .getAllByRole("button")
      .filter((b) => b.className.includes("bg-blue-600"));
    const pressed2 = within(row2)
      .getAllByRole("button")
      .filter((b) => b.className.includes("bg-blue-600"));

    expect(pressed1).toHaveLength(1);
    expect(pressed1[0]).toHaveTextContent("Choix A");
    expect(pressed2).toHaveLength(1);
    expect(pressed2[0]).toHaveTextContent("Choix B");
  });

  it("does not highlight any button when uxChoice is undefined (fresh anomaly)", () => {
    const CHOICES = [
      { label: "Choix 1", outcome: "o1" },
      { label: "Choix 2", outcome: "o2" },
    ];

    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            uxChoices: CHOICES,
            // uxChoice intentionally omitted
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    for (const c of CHOICES) {
      const btn = screen.getByRole("button", { name: c.label });
      expect(btn.className).not.toContain("bg-blue-600");
    }
  });

  it("does not highlight any button when uxChoice matches no listed outcome (stale choice)", () => {
    const CHOICES = [
      { label: "Choix X", outcome: "outcome_x" },
      { label: "Choix Y", outcome: "outcome_y" },
    ];

    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            uxChoices: CHOICES,
            uxChoice: "outcome_removed_from_catalog",
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    for (const c of CHOICES) {
      const btn = screen.getByRole("button", { name: c.label });
      expect(btn.className).not.toContain("bg-blue-600");
    }
  });

  it("renders group headers for every canonical domain when all are present", () => {
    // One anomaly per domain — verifies that DOMAIN_LABELS keys line up with domainOf().
    const anomalies: OrderAnomaly[] = [
      anomaly({ anomalyId: "d", issueDomain: "DOCUMENT", message: "doc" }),
      anomaly({ anomalyId: "p", issueDomain: "PARTNER", message: "part" }),
      anomaly({ anomalyId: "dup", issueDomain: "DUPLICATE", message: "dup" }),
      anomaly({ anomalyId: "a", issueDomain: "ARTICLE", message: "art" }),
      anomaly({ anomalyId: "o", issueDomain: "ORDER", message: "ord" }),
      anomaly({ anomalyId: "e", issueDomain: "EDI", message: "edi" }),
      anomaly({ anomalyId: "l", issueDomain: "DELIVERY", message: "liv" }),
      anomaly({ anomalyId: "t", issueDomain: "TECHNICAL", message: "tech" }),
    ];

    render(
      <AnomaliesTable
        anomalies={anomalies}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    for (const label of ["Document", "Partenaire", "Doublon", "Article", "Commande", "EDI", "Livraison", "Technique"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("preserves the canonical DOCUMENT → PARTNER → DUPLICATE → ARTICLE → ORDER → EDI → DELIVERY → TECHNICAL order regardless of input order", () => {
    const shuffled: OrderAnomaly[] = [
      anomaly({ anomalyId: "t", issueDomain: "TECHNICAL", message: "tech" }),
      anomaly({ anomalyId: "l", issueDomain: "DELIVERY", message: "liv" }),
      anomaly({ anomalyId: "a", issueDomain: "ARTICLE", message: "art" }),
      anomaly({ anomalyId: "d", issueDomain: "DOCUMENT", message: "doc" }),
      anomaly({ anomalyId: "p", issueDomain: "PARTNER", message: "part" }),
      anomaly({ anomalyId: "dup", issueDomain: "DUPLICATE", message: "dup" }),
      anomaly({ anomalyId: "o", issueDomain: "ORDER", message: "ord" }),
      anomaly({ anomalyId: "e", issueDomain: "EDI", message: "edi" }),
    ];

    render(
      <AnomaliesTable
        anomalies={shuffled}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const expected = ["Document", "Partenaire", "Doublon", "Article", "Commande", "EDI", "Livraison", "Technique"];
    const labels = Array.from(document.querySelectorAll("td, th"))
      .map((el) => el.textContent?.trim() ?? "")
      .filter((text) => expected.includes(text));

    expect(labels).toEqual(expected);
  });

  it("relegates unknown domain to the end of the list in alphabetical order", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({ anomalyId: "z", issueDomain: "ZOO" as OrderAnomaly["issueDomain"], message: "zoo" }),
          anomaly({ anomalyId: "d", issueDomain: "DOCUMENT", message: "doc" }),
          anomaly({ anomalyId: "y", issueDomain: "YAK" as OrderAnomaly["issueDomain"], message: "yak" }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const cellTexts = Array.from(document.querySelectorAll("td, th"))
      .map((el) => el.textContent?.trim() ?? "");
    const iDoc = cellTexts.indexOf("Document");
    const iYak = cellTexts.indexOf("YAK");
    const iZoo = cellTexts.indexOf("ZOO");

    expect(iDoc).toBeLessThan(iYak);
    expect(iYak).toBeLessThan(iZoo);
  });

  it("dispatches onChoose regardless of the current uxChoice (allows re-choice)", async () => {
    const user = userEvent.setup();
    const CHOICES = [
      { label: "Choix A", outcome: "outcome_a" },
      { label: "Choix B", outcome: "outcome_b" },
    ];

    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "a-rechoice",
            uxChoices: CHOICES,
            uxChoice: "outcome_a",
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    // Click the same choice again — the component should still dispatch (backend may accept or reject)
    await user.click(screen.getByRole("button", { name: "Choix A" }));
    expect(onChoose).toHaveBeenLastCalledWith("a-rechoice", "outcome_a");

    // Click a different choice — dispatch its outcome
    await user.click(screen.getByRole("button", { name: "Choix B" }));
    expect(onChoose).toHaveBeenLastCalledWith("a-rechoice", "outcome_b");
    expect(onChoose).toHaveBeenCalledTimes(2);
  });

  it("does not dispatch onChoose when the button is disabled (locked workflow)", async () => {
    const user = userEvent.setup();
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            uxChoices: [{ label: "Ne peut pas cliquer", outcome: "no_op" }],
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
        disabled
      />,
    );

    await user.click(screen.getByRole("button", { name: "Ne peut pas cliquer" }));
    expect(onChoose).not.toHaveBeenCalled();
  });

  it("keeps row selection independent from choice buttons (click on a button does not toggle row selection)", async () => {
    const user = userEvent.setup();

    const { rerender } = render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "an-scope",
            message: "Anomalie test",
            uxChoices: [{ label: "Choix", outcome: "outcome" }],
          }),
        ]}
        selectedAnomalyId="an-scope"
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    // The row is already selected — clicking the choice button must not deselect it.
    await user.click(screen.getByRole("button", { name: "Choix" }));

    expect(onChoose).toHaveBeenCalledWith("an-scope", "outcome");
    expect(onSelect).not.toHaveBeenCalled();

    // But clicking the message cell should toggle selection off.
    rerender(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "an-scope",
            message: "Anomalie test",
            uxChoices: [{ label: "Choix", outcome: "outcome" }],
          }),
        ]}
        selectedAnomalyId="an-scope"
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );
    await user.click(screen.getByText("Anomalie test"));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("shows the anomaly status verbatim in the aria-label for screen readers", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({ anomalyId: "s-1", message: "Statut ouverte", status: "Ouverte" }),
          anomaly({ anomalyId: "s-2", message: "Statut corrigée", status: "Corrigée" }),
          anomaly({ anomalyId: "s-3", message: "Statut bloquante", status: "Bloquante" }),
          anomaly({ anomalyId: "s-4", message: "Statut ignorée", status: "Ignorée" }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.getByRole("row", { name: /Statut ouverte\. Statut Ouverte/i })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Statut corrigée\. Statut Corrigée/i })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Statut bloquante\. Statut Bloquante/i })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Statut ignorée\. Statut Ignorée/i })).toBeInTheDocument();
  });

  it("marks the selected row with aria-selected=true and data-state=selected", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({ anomalyId: "sel-a", message: "Selected row" }),
          anomaly({ anomalyId: "sel-b", message: "Other row" }),
        ]}
        selectedAnomalyId="sel-a"
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const selectedRow = screen.getByRole("row", { name: /Selected row/i });
    const otherRow = screen.getByRole("row", { name: /Other row/i });

    expect(selectedRow).toHaveAttribute("aria-selected", "true");
    expect(selectedRow).toHaveAttribute("data-state", "selected");
    expect(otherRow).toHaveAttribute("aria-selected", "false");
    expect(otherRow).not.toHaveAttribute("data-state");
  });

  it("keyboard: Enter toggles selection off when the row is already selected", async () => {
    const user = userEvent.setup();
    render(
      <AnomaliesTable
        anomalies={[anomaly({ anomalyId: "kb-toggle", message: "row" })]}
        selectedAnomalyId="kb-toggle"
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const row = screen.getByRole("row", { name: /row/i });
    row.focus();
    await user.keyboard("{Enter}");

    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("comments filter is stable when the anomaly has no comments (does not render a stray '0 note')", () => {
    render(
      <AnomaliesTable
        anomalies={[anomaly({ anomalyId: "no-comments", message: "row" })]}
        comments={[]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.queryByText(/0 note/i)).not.toBeInTheDocument();
  });

  /**
   * Dual-display invariant: the row shows `message` (the specific text from
   * rejection_catalog.format_rejection_message — dynamic per-line details for
   * MATERIAL_STATUS_INVALID, PO_NUMBER_DUPLICATE, QUANTITY_MISSING, etc.) as
   * the primary line, and `uxMessage` (the general framing from ux_catalog)
   * as a subtitle when both exist and differ. Ensures no message-level
   * information is silently dropped for any rule.
   */
  it("dual-display: shows message as primary and uxMessage as secondary when both are set and different", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "an-ux13",
            message: "Ce numéro de commande PO-42 existe déjà dans l'historique SAP.",
            uxMessage: "Génie a identifié un numéro de commande déjà présent dans l'historique SAP",
            uxId: "UX-13",
            uxChoices: [{ label: "J'ai vérifié : c'est une nouvelle commande", outcome: "confirm_new_order_and_recontrol" }],
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    // Both are visible → primary specific text + secondary framing.
    expect(screen.getByText(/PO-42 existe déjà dans l'historique SAP/i)).toBeInTheDocument();
    expect(screen.getByText(/Génie a identifié un numéro de commande déjà présent/i)).toBeInTheDocument();
  });

  it("dual-display: falls back to uxMessage when message is empty", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "an-fallback",
            message: "",
            uxMessage: "Génie n'a pas pu identifier le sold-to",
            uxChoices: [{ label: "J'ai corrigé le Sold-to", outcome: "correct_and_recontrol" }],
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.getByText(/Génie n'a pas pu identifier le sold-to/i)).toBeInTheDocument();
  });

  it("dual-display: renders no secondary line when uxMessage equals message (no duplicate)", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({ anomalyId: "an-eq", message: "Identique", uxMessage: "Identique" }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );
    expect(screen.getAllByText("Identique")).toHaveLength(1);
  });

  /**
   * ADV validation truth table (row 12, UX-08): when uxMessage is null (as it is
   * for MATERIAL_STATUS_INVALID after the src/ux_catalog.py fix), the specific
   * per-line message produced by src.masterdata_runtime.build_material_status_message
   * surfaces verbatim ("Ligne 3 : la référence X a été remplacée depuis
   * le jj/mm/aaaa par Y", etc.).
   */
  it("UX-08: specific per-line message wins when uxMessage is null", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "an-ux08-mat",
            message: "Ligne 3 : la référence 7738201234 a été remplacée depuis le 15/09/2026 par 7738209876",
            uxMessage: null,
            uxId: "UX-08",
            uxChoices: [
              { label: "J'ai remplacé ou corrigé la référence article", outcome: "correct_and_recontrol" },
            ],
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(
      screen.getByText(/référence 7738201234 a été remplacée .* par 7738209876/i),
    ).toBeInTheDocument();
    // The generic framing is NOT displayed (uxMessage is null).
    expect(
      screen.queryByText(/n'a pas pu valider la référence article/i),
    ).not.toBeInTheDocument();
  });
});
