import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, ApiError, apiStream, SessionExpiredError } from "./apiClient";

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

  it("distinguishes an exhausted daily budget from a rate limit", async () => {
    mockFetchOnce(429, { error: "daily token budget exhausted" });
    const error = await apiFetch("/api/chat/threads/t1/messages", { method: "POST" }).catch((e) => e);
    expect(error.message).toMatch(/today's limit/i);
    expect(error.message).not.toMatch(/too quickly/);
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

  it("treats a 401 on a token-bearing request as an expired session", async () => {
    mockFetchOnce(401, { error: "Token has expired" });
    const error = await apiFetch("/api/chat/threads", { token: "tok123" }).catch((e) => e);
    expect(error).toBeInstanceOf(SessionExpiredError);
    expect(error.message).toMatch(/session has expired/i);
  });

  it("leaves a 401 without a token as a credentials failure", async () => {
    mockFetchOnce(401, { error: "invalid email or password" });
    const error = await apiFetch("/api/auth/login", { method: "POST" }).catch((e) => e);
    expect(error).not.toBeInstanceOf(SessionExpiredError);
    expect(error.message).toBe("invalid email or password");
  });

  it("treats an unusable token as an expired session", async () => {
    // flask-jwt-extended answers 422 for a token it cannot decode.
    mockFetchOnce(422, { msg: "Not enough segments" });
    const error = await apiFetch("/api/chat/threads", { token: "corrupted" }).catch((e) => e);
    expect(error).toBeInstanceOf(SessionExpiredError);
  });

  it("keeps a validation failure distinct from a dead session", async () => {
    // The API's own 422 carries "error"/"details", never "msg".
    mockFetchOnce(422, { error: "validation failed", details: [{ field: "title" }] });
    const error = await apiFetch("/api/chat/threads", { method: "POST", token: "tok123" }).catch((e) => e);
    expect(error).not.toBeInstanceOf(SessionExpiredError);
    expect(error.message).toBe("validation failed");
    expect(error.details).toEqual([{ field: "title" }]);
  });
});

function streamOf(...chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
      controller.close();
    },
  });
}

// A body whose connection drops after the first chunk, with `failure` as the
// browser's rejection, and a cancel to watch.
function droppingBody(chunk, failure) {
  const read = vi
    .fn()
    .mockResolvedValueOnce({ value: new TextEncoder().encode(chunk), done: false })
    .mockRejectedValueOnce(failure);
  const cancel = vi.fn().mockResolvedValue(undefined);
  return { getReader: () => ({ read, cancel }), cancel };
}

describe("apiStream", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts the body with the token and hands each event to onEvent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: streamOf('event: delta\ndata: {"text":"a"}\n\n', 'event: done\ndata: {"ok":true}'),
      }),
    );
    const onEvent = vi.fn();
    await apiStream("/api/chat/threads/t1/messages/stream", { token: "tok", body: { content: "Q" }, onEvent });
    expect(onEvent.mock.calls.map(([e]) => e)).toEqual([
      { event: "delta", data: { text: "a" } },
      { event: "done", data: { ok: true } },
    ]);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toMatch(/\/api\/chat\/threads\/t1\/messages\/stream$/);
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer tok");
    expect(options.headers.Accept).toBe("text/event-stream");
    expect(JSON.parse(options.body)).toEqual({ content: "Q" });
  });

  it("rejects with the budget message on a budget 429", async () => {
    mockFetchOnce(429, { error: "daily token budget exhausted" });
    const error = await apiStream("/x", { token: "tok", body: {}, onEvent: vi.fn() }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toMatch(/today's limit/i);
  });

  it("rejects with SessionExpiredError on a 401 with a token", async () => {
    mockFetchOnce(401, { msg: "Token has expired" });
    const error = await apiStream("/x", { token: "tok", body: {}, onEvent: vi.fn() }).catch((e) => e);
    expect(error).toBeInstanceOf(SessionExpiredError);
  });

  it("rethrows an abort as an AbortError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
    const error = await apiStream("/x", { token: "tok", body: {}, onEvent: vi.fn() }).catch((e) => e);
    expect(error.name).toBe("AbortError");
  });

  it("says PolicyPal can't be reached when the connection drops mid-stream, and lets the reader go", async () => {
    const body = droppingBody('event: delta\ndata: {"text":"a"}\n\n', new TypeError("network error"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, body }));
    const onEvent = vi.fn();

    const error = await apiStream("/x", { token: "tok", body: {}, onEvent }).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toMatch(/Can't reach PolicyPal/);
    expect(error.message).not.toMatch(/network error/);
    expect(onEvent).toHaveBeenCalledWith({ event: "delta", data: { text: "a" } });
    expect(body.cancel).toHaveBeenCalledOnce();
  });

  it("rethrows an abort mid-stream as the AbortError it is, and lets the reader go", async () => {
    const body = droppingBody('event: stage\ndata: {"stage":"searching"}\n\n', new DOMException("aborted", "AbortError"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, body }));

    const error = await apiStream("/x", { token: "tok", body: {}, onEvent: vi.fn() }).catch((e) => e);

    expect(error.name).toBe("AbortError");
    expect(body.cancel).toHaveBeenCalledOnce();
  });

  it("says PolicyPal can't be reached when the network fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiStream("/x", { token: "tok", body: {}, onEvent: vi.fn() })).rejects.toThrow(
      /Can't reach PolicyPal/,
    );
  });
});
