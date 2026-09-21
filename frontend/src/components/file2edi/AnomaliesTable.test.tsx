import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { OrderAnomaly, OrderComment } from "@/types";
import { AnomaliesTable } from "./AnomaliesTable";

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

const CHOICES_ORDER_KEY = [
  { label: "J'ai renseigné le numéro de commande", outcome: "correct_and_recontrol" },
  { label: "J'ai vérifié : l'information n'est pas présente sur le document", outcome: "keep_blocked" },
];

const CHOICES_DUPLICATE_PO = [
  { label: "J'ai vérifié : c'est une nouvelle commande", outcome: "confirm_new_order_and_recontrol" },
  { label: "J'ai vérifié : cette commande existe déjà dans SAP", outcome: "keep_blocked" },
];

describe("AnomaliesTable", () => {
  let onSelect: ReturnType<typeof vi.fn>;
  let onChoose: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onSelect = vi.fn();
    onChoose = vi.fn();
  });

  it("renders an empty state when no anomalies are provided", () => {
    render(
      <AnomaliesTable
        anomalies={[]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.getByText("Aucune anomalie.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("groups anomalies by domain in the canonical order (DOCUMENT before PARTNER before ARTICLE)", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({ anomalyId: "art", issueDomain: "ARTICLE", message: "Article invalide" }),
          anomaly({ anomalyId: "part", issueDomain: "PARTNER", message: "Sold-to inconnu" }),
          anomaly({ anomalyId: "doc", issueDomain: "DOCUMENT", message: "Document invalide" }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    // group headers are rendered as cells with domain labels in FR
    const headers = ["Document", "Partenaire", "Article"];
    const positions = headers.map((label) => {
      const el = screen.getByText(label);
      const cells = Array.from(document.querySelectorAll("td, th"));
      return cells.indexOf(el.closest("td, th") as Element);
    });

    expect(positions[0]).toBeGreaterThanOrEqual(0);
    expect(positions[0]).toBeLessThan(positions[1]);
    expect(positions[1]).toBeLessThan(positions[2]);
  });

  it("falls back to TECHNICAL when issueDomain is missing", () => {
    render(
      <AnomaliesTable
        anomalies={[anomaly({ issueDomain: undefined })]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.getByText("Technique")).toBeInTheDocument();
  });

  it("renders one button per uxChoice with its label", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            uxId: "UX-03",
            uxChoices: CHOICES_ORDER_KEY,
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    for (const choice of CHOICES_ORDER_KEY) {
      expect(screen.getByRole("button", { name: choice.label })).toBeInTheDocument();
    }
  });

  it("calls onChoose with anomalyId and outcome when a choice button is clicked", async () => {
    const user = userEvent.setup();

    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "an-42",
            uxChoices: CHOICES_ORDER_KEY,
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "J'ai renseigné le numéro de commande" }),
    );

    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith("an-42", "correct_and_recontrol");
  });

  it("does not propagate the button click to row selection", async () => {
    const user = userEvent.setup();

    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "an-1",
            uxChoices: CHOICES_ORDER_KEY,
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "J'ai renseigné le numéro de commande" }),
    );

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("disables all choice buttons when disabled prop is true", () => {
    render(
      <AnomaliesTable
        anomalies={[anomaly({ uxChoices: CHOICES_ORDER_KEY })]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
        disabled
      />,
    );

    for (const choice of CHOICES_ORDER_KEY) {
      expect(screen.getByRole("button", { name: choice.label })).toBeDisabled();
    }
  });

  it("highlights the currently selected uxChoice (bg-blue-600 on the matching button)", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            uxChoices: CHOICES_ORDER_KEY,
            uxChoice: "correct_and_recontrol",
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const selected = screen.getByRole("button", { name: "J'ai renseigné le numéro de commande" });
    const other = screen.getByRole("button", {
      name: "J'ai vérifié : l'information n'est pas présente sur le document",
    });

    expect(selected.className).toContain("bg-blue-600");
    expect(other.className).not.toContain("bg-blue-600");
  });

  it("renders no button when uxChoices is empty (SYSTEM-resolved anomalies)", () => {
    render(
      <AnomaliesTable
        anomalies={[anomaly({ uxChoices: [] })]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    // No choice buttons should appear (rowgroup / table exists but action cell is empty)
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("selects a row when clicked, deselects when clicked again, and calls onSelectAnomaly", async () => {
    const user = userEvent.setup();

    const { rerender } = render(
      <AnomaliesTable
        anomalies={[anomaly({ anomalyId: "an-select" })]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const rows = screen.getAllByRole("row");
    // 1 header row + 1 domain header row + 1 data row → data row is last
    const dataRow = rows[rows.length - 1];

    await user.click(dataRow);
    expect(onSelect).toHaveBeenLastCalledWith("an-select");

    rerender(
      <AnomaliesTable
        anomalies={[anomaly({ anomalyId: "an-select" })]}
        selectedAnomalyId="an-select"
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const refreshedRows = screen.getAllByRole("row");
    const refreshedDataRow = refreshedRows[refreshedRows.length - 1];
    expect(refreshedDataRow).toHaveAttribute("aria-selected", "true");

    await user.click(refreshedDataRow);
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("toggles selection on Enter and Space key press", async () => {
    const user = userEvent.setup();

    render(
      <AnomaliesTable
        anomalies={[anomaly({ anomalyId: "an-kb" })]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const rows = screen.getAllByRole("row");
    const dataRow = rows[rows.length - 1];
    dataRow.focus();

    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith("an-kb");

    await user.keyboard(" ");
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("shows a severity badge in French for each severity level", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({ anomalyId: "s1", issueSeverity: "CRITICAL", message: "msg-crit" }),
          anomaly({ anomalyId: "s2", issueSeverity: "ERROR", message: "msg-err" }),
          anomaly({ anomalyId: "s3", issueSeverity: "WARNING", message: "msg-warn" }),
          anomaly({ anomalyId: "s4", issueSeverity: "INFO", message: "msg-info" }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.getByText("Critique")).toBeInTheDocument();
    expect(screen.getByText("Erreur")).toBeInTheDocument();
    expect(screen.getByText("Avertissement")).toBeInTheDocument();
    expect(screen.getByText("Info")).toBeInTheDocument();
  });

  it("renders uxMessage as a secondary line when it differs from the main message", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            message: "ORDER_KEY_MISSING",
            uxMessage: "Génie n'a pas pu identifier le numéro de commande d'achat",
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(
      screen.getByText("Génie n'a pas pu identifier le numéro de commande d'achat"),
    ).toBeInTheDocument();
  });

  it("hides uxMessage when it is identical to the main message (no duplicate line)", () => {
    render(
      <AnomaliesTable
        anomalies={[anomaly({ message: "Même message", uxMessage: "Même message" })]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.getAllByText("Même message")).toHaveLength(1);
  });

  it("shows the comment count for each anomaly (singular vs plural)", () => {
    const comments: OrderComment[] = [
      {
        commentId: "c1",
        orderId: "o-1",
        anomalyId: "a1",
        actor: "khadara",
        body: "note 1",
        createdAt: "2026-09-21T10:00:00Z",
      },
      {
        commentId: "c2",
        orderId: "o-1",
        anomalyId: "a1",
        actor: "khadara",
        body: "note 2",
        createdAt: "2026-09-21T10:01:00Z",
      },
      {
        commentId: "c3",
        orderId: "o-1",
        anomalyId: "a2",
        actor: "khadara",
        body: "note single",
        createdAt: "2026-09-21T10:02:00Z",
      },
    ];

    render(
      <AnomaliesTable
        anomalies={[
          anomaly({ anomalyId: "a1", message: "First" }),
          anomaly({ anomalyId: "a2", message: "Second" }),
        ]}
        comments={comments}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.getByText("2 notes")).toBeInTheDocument();
    expect(screen.getByText("1 note")).toBeInTheDocument();
  });

  it("exposes an accessible table label", () => {
    render(
      <AnomaliesTable
        anomalies={[anomaly()]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    expect(screen.getByRole("table", { name: "Anomalies de la commande" })).toBeInTheDocument();
  });

  it("renders the anomaly message alongside the choice button label (independent cells)", () => {
    render(
      <AnomaliesTable
        anomalies={[
          anomaly({
            anomalyId: "a-dup",
            issueDomain: "DUPLICATE",
            message: "Doublon détecté",
            uxChoices: CHOICES_DUPLICATE_PO,
          }),
        ]}
        selectedAnomalyId={null}
        onSelectAnomaly={onSelect}
        onChoose={onChoose}
      />,
    );

    const row = screen.getByRole("row", { name: /Doublon détecté/i });
    const buttons = within(row).getAllByRole("button");
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveTextContent("J'ai vérifié : c'est une nouvelle commande");
  });
});
