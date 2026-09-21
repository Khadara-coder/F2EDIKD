import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

type FetchMock = ReturnType<typeof vi.fn>;

function mockJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockErrorResponse(body: unknown, status = 400): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mock204Response(): Response {
  return new Response(null, { status: 204 });
}

describe("api client — anomaly endpoints", () => {
  let fetchMock: FetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("resolveAnomaly", () => {
    it("sends a PATCH to /api/orders/anomalies/{id} with action=choice and outcome/justification", async () => {
      fetchMock.mockResolvedValueOnce(mockJsonResponse({ anomalies: [] }));

      await api.resolveAnomaly("an-42", "choice", {
        outcome: "correct_and_recontrol",
        justification: "vérifié",
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe("/api/orders/anomalies/an-42");
      expect(init).toMatchObject({ method: "PATCH", credentials: "include" });
      expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
      expect(JSON.parse(init.body as string)).toEqual({
        action: "choice",
        outcome: "correct_and_recontrol",
        justification: "vérifié",
      });
    });

    it("still supports the legacy actions (corrected / ignored / blocking) without payload", async () => {
      fetchMock.mockResolvedValueOnce(mockJsonResponse({}));

      await api.resolveAnomaly("an-1", "corrected");

      const [, init] = fetchMock.mock.calls[0];
      expect(JSON.parse(init.body as string)).toEqual({ action: "corrected" });
    });

    it("propagates the backend error message via ApiError (HTTP 400 justification required)", async () => {
      fetchMock.mockResolvedValueOnce(
        mockErrorResponse({ detail: "Une justification est obligatoire pour ce choix" }, 400),
      );

      try {
        await api.resolveAnomaly("an-1", "choice", { outcome: "confirm_new_order_and_recontrol" });
        expect.fail("expected ApiError to be thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(400);
        expect((err as ApiError).message).toBe(
          "Une justification est obligatoire pour ce choix",
        );
      }
    });
  });

  describe("recontrolAnomaly", () => {
    it("sends a POST to /api/orders/anomalies/{id}/recontrol with no body", async () => {
      fetchMock.mockResolvedValueOnce(mockJsonResponse({ anomalies: [] }));

      await api.recontrolAnomaly("an-99");

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe("/api/orders/anomalies/an-99/recontrol");
      expect(init).toMatchObject({ method: "POST", credentials: "include" });
      expect(init.body).toBeUndefined();
    });

    it("returns undefined on HTTP 204 (no content)", async () => {
      fetchMock.mockResolvedValueOnce(mock204Response());

      const result = await api.recontrolAnomaly("an-1");

      expect(result).toBeUndefined();
    });

    it("throws ApiError on 500 with the fallback message", async () => {
      fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

      await expect(api.recontrolAnomaly("an-1")).rejects.toMatchObject({
        name: "ApiError",
        status: 500,
      });
    });
  });

  describe("request wrapper contract", () => {
    it("always includes credentials for cookie-based auth (f2edi_session)", async () => {
      fetchMock.mockResolvedValueOnce(mockJsonResponse({}));

      await api.recontrolAnomaly("x");

      const [, init] = fetchMock.mock.calls[0];
      expect(init.credentials).toBe("include");
    });

    it("extracts message from body.detail preferentially, then body.message, then body.error", async () => {
      fetchMock.mockResolvedValueOnce(mockErrorResponse({ message: "explicit message" }, 422));

      try {
        await api.recontrolAnomaly("x");
        expect.fail("expected ApiError");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).message).toBe("explicit message");
      }
    });
  });
});
