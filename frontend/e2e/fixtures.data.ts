/**
 * Fixture builders for E2E mocked specs. Keep these narrow — every field the UI reads
 * from the review must have a sensible default so tests can override only what they care about.
 */

import type { CurrentUser, OrderReview, OrderAnomaly, SystemHealth } from "../src/types";

export const MOCK_ORDER_ID = "mock-order-1";

export function mockCurrentUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    actor: "e2e-user",
    username: "e2e-user",
    displayName: "E2E User",
    role: "adv",
    authenticated: true,
    ...overrides,
  };
}

export function mockSystemHealth(): SystemHealth {
  return {
    api: "connected",
    database: "connected",
    csv: "connected",
    sftp: "connected",
  };
}

export function mockAnomaly(overrides: Partial<OrderAnomaly> = {}): OrderAnomaly {
  return {
    anomalyId: "an-1",
    orderId: MOCK_ORDER_ID,
    severity: "error",
    message: "ORDER_KEY_MISSING",
    status: "Ouverte",
    createdAt: "2026-09-21T10:00:00Z",
    issueDomain: "ORDER",
    issueSeverity: "ERROR",
    ...overrides,
  };
}

export function mockOrderReview(overrides: Partial<OrderReview> = {}): OrderReview {
  return {
    order: {
      orderId: MOCK_ORDER_ID,
      uploadId: "upl-1",
      fileName: "mock-order.pdf",
      clientName: "Client Test",
      customerOrderNumber: "",
      documentReference: "REF-1",
      orderDate: null,
      requestedDeliveryDate: null,
      currency: "EUR",
      incoterm: "",
      deliveryMode: "",
      messageType: "ORDERS",
      vendor: "",
      totalAmount: 0,
      globalConfidence: 90,
      status: "review_required",
      reviewRequired: true,
      lineCount: 1,
      createdAt: "2026-09-21T10:00:00Z",
      updatedAt: "2026-09-21T10:00:00Z",
    },
    partners: [],
    lines: [],
    anomalies: [],
    comments: [],
    traceability: [],
    edifactReady: false,
    ...overrides,
  };
}
