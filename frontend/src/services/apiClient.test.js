import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, ApiError } from "./apiClient";

function mockFetchOnce(status, body) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status,
      ok: status >= 200 && status < 300,
      json: () => Promise.resolve(body),
    }),
  );
}

describe("apiFetch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON on success", async () => {
    mockFetchOnce(200, { ok: true });
    const data = await apiFetch("/api/auth/me", { token: "tok123" });
    expect(data).toEqual({ ok: true });
  });

  it("attaches the bearer token when provided", async () => {
    mockFetchOnce(200, {});
    await apiFetch("/api/auth/me", { token: "tok123" });
    const [, options] = fetch.mock.calls[0];
    expect(options.headers.Authorization).toBe("Bearer tok123");
  });

  it("returns null for a 204 response", async () => {
    mockFetchOnce(204, null);
    const data = await apiFetch("/api/chat/threads/t1", { method: "DELETE", token: "tok123" });
    expect(data).toBeNull();
  });

  it("raises a friendly message on 429", async () => {
    mockFetchOnce(429, { error: "rate limited" });
    await expect(apiFetch("/api/auth/login", { method: "POST" })).rejects.toThrow(/too quickly/);
  });

  it("raises the server's error message on other failures", async () => {
    mockFetchOnce(409, { error: "an account with this email already exists" });
    const error = await apiFetch("/api/auth/register", { method: "POST" }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe("an account with this email already exists");
    expect(error.status).toBe(409);
  });

  it("raises a friendly message when the network request itself fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(apiFetch("/api/auth/me", { token: "tok123" })).rejects.toThrow(/Can't reach PolicyPal/);
  });
});
