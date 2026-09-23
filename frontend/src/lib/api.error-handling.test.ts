import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

/**
 * Complements api.test.ts with deep coverage of the shared request wrapper's
 * error-handling logic. Every branch of the message-extraction chain
 * (body.message → body.detail → body.error → array of {msg} → raw text →
 * fallback `HTTP ${status}`) is exercised so a regression on this critical
 * error-reporting path fails loudly.
 */

type FetchMock = ReturnType<typeof vi.fn>;

function response(body: unknown, status = 200, contentType = "application/json"): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "Content-Type": contentType },
  });
}

describe("api client — error extraction chain", () => {
  let fetchMock: FetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("prefers body.message over body.detail when both are present", async () => {
    fetchMock.mockResolvedValueOnce(
      response({ message: "message win", detail: "detail lose" }, 400),
    );

    await expect(api.recontrolAnomaly("x")).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      message: "message win",
    });
  });

  it("falls back to body.detail when body.message is missing", async () => {
    fetchMock.mockResolvedValueOnce(response({ detail: "detail message" }, 400));

    await expect(api.recontrolAnomaly("x")).rejects.toMatchObject({
      message: "detail message",
    });
  });

  it("falls back to body.error when neither message nor detail are set", async () => {
    fetchMock.mockResolvedValueOnce(response({ error: "error message" }, 400));

    await expect(api.recontrolAnomaly("x")).rejects.toMatchObject({
      message: "error message",
    });
  });

  it("joins array-of-{msg} into a comma-separated message (FastAPI validation errors)", async () => {
    fetchMock.mockResolvedValueOnce(
      response(
        {
          detail: [
            { msg: "field a required" },
            { msg: "field b invalid" },
          ],
        },
        422,
      ),
    );

    await expect(api.recontrolAnomaly("x")).rejects.toMatchObject({
      status: 422,
      message: "field a required, field b invalid",
    });
  });

  it("uses the raw text body when it is not JSON (truncated to 400 chars)", async () => {
    const longText = "x".repeat(1000);
    fetchMock.mockResolvedValueOnce(new Response(longText, { status: 502 }));

    let caught: ApiError | undefined;
    try {
      await api.recontrolAnomaly("x");
    } catch (err) {
      caught = err as ApiError;
    }

    expect(caught).toBeInstanceOf(ApiError);
    expect(caught?.status).toBe(502);
    expect(caught?.message).toHaveLength(400);
    expect(caught?.message).toBe("x".repeat(400));
  });

  it("falls back to `HTTP {status}` when the body is empty", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 500 }));

    await expect(api.recontrolAnomaly("x")).rejects.toMatchObject({
      status: 500,
      message: "HTTP 500",
    });
  });

  it("propagates the raw JSON body via ApiError.detail for programmatic access", async () => {
    fetchMock.mockResolvedValueOnce(
      response({ detail: "boom", errorCode: "E-42", context: { foo: "bar" } }, 400),
    );

    let caught: ApiError | undefined;
    try {
      await api.recontrolAnomaly("x");
    } catch (err) {
      caught = err as ApiError;
    }

    expect(caught?.detail).toBe("boom");
  });

  it("rethrows fetch-level errors (network unreachable) with the original TypeError shape", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    let caught: unknown;
    try {
      await api.recontrolAnomaly("x");
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(TypeError);
    expect((caught as Error).message).toMatch(/Failed to fetch/);
  });
});

describe("api client — resolveAnomaly payload shapes", () => {
  let fetchMock: FetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends only {action, outcome} when justification is omitted", async () => {
    fetchMock.mockResolvedValueOnce(response({}));

    await api.resolveAnomaly("an-1", "choice", { outcome: "correct_and_recontrol" });

    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ action: "choice", outcome: "correct_and_recontrol" });
    expect(body).not.toHaveProperty("justification");
  });

  it("sends justification as-is when it is a non-empty string", async () => {
    fetchMock.mockResolvedValueOnce(response({}));

    await api.resolveAnomaly("an-1", "choice", {
      outcome: "confirm_new_order_and_recontrol",
      justification: "  vérifié avec le client  ",
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body as string)).toMatchObject({
      justification: "  vérifié avec le client  ",
    });
  });

  it.each([
    "correct_and_recontrol",
    "confirm_and_recontrol",
    "keep_blocked",
    "keep_blocked_and_escalate",
    "confirm_new_order_and_recontrol",
    "confirm_distinct_order_and_recontrol",
    "confirm_no_price_and_recontrol",
    "delete_line_and_recontrol",
    "correct_and_regenerate",
    "regenerate_and_recontrol",
    "close_without_sap",
    "retry_delivery",
    "confirm_manual_delivery",
    "retry_masterdata_check",
  ])("propagates outcome=%s verbatim in the PATCH body", async (outcome) => {
    fetchMock.mockResolvedValueOnce(response({}));

    await api.resolveAnomaly("an-1", "choice", { outcome });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body as string)).toMatchObject({ action: "choice", outcome });
  });

  it("URL-encodes nothing — the anomalyId is expected to already be safe", async () => {
    fetchMock.mockResolvedValueOnce(response({}));

    await api.resolveAnomaly("an-with-dashes-and-uuid-abc123", "choice", { outcome: "keep_blocked" });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/orders/anomalies/an-with-dashes-and-uuid-abc123");
  });
});
