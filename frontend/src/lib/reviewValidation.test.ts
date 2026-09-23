import { describe, expect, it } from "vitest";
import type { OrderAnomaly } from "@/types";
import {
  countPendingAnomalies,
  collectReviewBlockers,
  isAnomalyPending,
} from "./reviewValidation";

function makeAnomaly(overrides: Partial<OrderAnomaly>): OrderAnomaly {
  return {
    anomalyId: "an-1",
    orderId: "ord-1",
    severity: "warning",
    message: "test",
    status: "Ouverte",
    createdAt: "2026-09-23T10:00:00Z",
    ...overrides,
  };
}

describe("isAnomalyPending", () => {
  it("returns true for Ouverte and Bloquante", () => {
    expect(isAnomalyPending(makeAnomaly({ status: "Ouverte" }))).toBe(true);
    expect(isAnomalyPending(makeAnomaly({ status: "Bloquante" }))).toBe(true);
  });
  it("returns false for Corrigée and Ignorée", () => {
    expect(isAnomalyPending(makeAnomaly({ status: "Corrigée" }))).toBe(false);
    expect(isAnomalyPending(makeAnomaly({ status: "Ignorée" }))).toBe(false);
  });
});

describe("countPendingAnomalies — blocking gate", () => {
  it("counts blocking anomalies that are Ouverte", () => {
    const anomalies = [
      makeAnomaly({ anomalyId: "a1", status: "Ouverte", blocking: true }),
      makeAnomaly({ anomalyId: "a2", status: "Corrigée", blocking: true }),
    ];
    expect(countPendingAnomalies(anomalies)).toBe(1);
  });

  it("does NOT count non-blocking article anomalies (blocking=false) even when Ouverte", () => {
    const anomalies = [
      makeAnomaly({ anomalyId: "a1", fieldName: "MATERIAL_STATUS_INVALID", status: "Ouverte", blocking: false }),
      makeAnomaly({ anomalyId: "a2", fieldName: "ARTICLE_NOT_FOUND", status: "Ouverte", blocking: false }),
      makeAnomaly({ anomalyId: "a3", fieldName: "NO_VALID_ARTICLE", status: "Ouverte", blocking: false }),
    ];
    expect(countPendingAnomalies(anomalies)).toBe(0);
  });

  it("counts anomaly with blocking=undefined as blocking (conservative default)", () => {
    const anomalies = [
      makeAnomaly({ anomalyId: "a1", status: "Ouverte" }), // blocking omitted
    ];
    expect(countPendingAnomalies(anomalies)).toBe(1);
  });

  it("SAP send unblocked: mix of resolved blocking + open article warnings", () => {
    const anomalies = [
      makeAnomaly({ anomalyId: "a1", fieldName: "SOLDTO_NOT_FOUND", status: "Corrigée", blocking: true }),
      makeAnomaly({ anomalyId: "a2", fieldName: "MATERIAL_STATUS_INVALID", status: "Ouverte", blocking: false }),
      makeAnomaly({ anomalyId: "a3", fieldName: "ARTICLE_NOT_FOUND", status: "Ouverte", blocking: false }),
    ];
    // Blocking anomaly is resolved → count = 0 → SAP send enabled
    expect(countPendingAnomalies(anomalies)).toBe(0);
  });

  it("NO_LINE_ITEMS still blocks when Ouverte (no valid lines scenario)", () => {
    const anomalies = [
      makeAnomaly({ anomalyId: "a1", fieldName: "NO_LINE_ITEMS", status: "Ouverte", blocking: true }),
    ];
    expect(countPendingAnomalies(anomalies)).toBe(1);
  });

  it("after delete_line_and_recontrol with valid lines remaining: article anomaly Corrigée + no blocking → count=0", () => {
    const anomalies = [
      makeAnomaly({ anomalyId: "a1", fieldName: "MATERIAL_STATUS_INVALID", status: "Corrigée", blocking: false }),
    ];
    expect(countPendingAnomalies(anomalies)).toBe(0);
  });
});

describe("collectReviewBlockers — non-blocking article anomalies excluded", () => {
  const baseOrder = {
    orderId: "o1", uploadId: "u1", fileName: "test.pdf", clientName: "Client",
    customerOrderNumber: "PO-001", documentReference: "REF-001",
    orderDate: "2026-09-23", requestedDeliveryDate: "2026-10-01",
    currency: "EUR", incoterm: "EXW", deliveryMode: "STANDARD",
    messageType: "ORDERS", vendor: "Bosch", totalAmount: 100,
    globalConfidence: 0.9, status: "Revue requise" as const,
    reviewRequired: true, lineCount: 2, createdAt: "2026-09-23T10:00:00Z",
    updatedAt: "2026-09-23T10:00:00Z",
  };
  const partners = [
    { partnerId: "p1", orderId: "o1", partnerFunction: "soldto" as const, partnerCode: "10001", partnerName: "Client SA", addressLine1: "1 rue Test", postalCode: "75001", city: "Paris", country: "FR", confidence: 0.9 },
    { partnerId: "p2", orderId: "o1", partnerFunction: "shipto" as const, partnerCode: "20001", partnerName: "Site livraison", addressLine1: "2 rue Test", postalCode: "75002", city: "Paris", country: "FR", confidence: 0.9 },
  ];
  const lines = [
    { lineId: "l1", orderId: "o1", lineNumber: 1, customerReference: "REF", boschArticle: "7736606771", designation: "Pièce", quantity: 2, unit: "PCE", unitPrice: 50, amount: 100, confidence: 0.9, status: "OK" as const },
  ];

  it("no blocking message when only article warnings remain open", () => {
    const anomalies = [
      makeAnomaly({ fieldName: "MATERIAL_STATUS_INVALID", status: "Ouverte", blocking: false }),
    ];
    const blockers = collectReviewBlockers(baseOrder, partners, lines, anomalies);
    expect(blockers).toHaveLength(0);
  });

  it("blocking message still shown for SOLDTO_NOT_FOUND open", () => {
    const anomalies = [
      makeAnomaly({ fieldName: "SOLDTO_NOT_FOUND", status: "Ouverte", blocking: true }),
    ];
    const blockers = collectReviewBlockers(baseOrder, partners, lines, anomalies);
    expect(blockers.some(b => b.includes("anomalie"))).toBe(true);
  });
});
