import { createSseParser } from "./sse";

// 127.0.0.1, not localhost: macOS AirPlay Receiver listens on *:5000, and
// localhost resolving to ::1 reaches it instead of Flask, which binds IPv4.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5000";

const UNREACHABLE = "Can't reach PolicyPal right now. Check your connection and try again.";

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export class SessionExpiredError extends ApiError {
  constructor() {
    super("Your session has expired. Sign in again to pick up where you left off.", 401);
  }
}

// The error a non-ok response stands for. Returned, not thrown, so a JSON
// request and a stream share it.
function errorFor(response, data, token) {
  // Only a request that carried a token can have a dead one. A 401 from
  // login means the credentials were wrong, which is a different message.
  // flask-jwt-extended answers 401 for an expired token and 422 for an
  // unusable one, both under "msg"; the API's own 422 carries "error"
  // instead, so a validation failure is never mistaken for a dead session.
  const rejectedTheToken = response.status === 401 || (response.status === 422 && data?.msg);
  if (rejectedTheToken && token) return new SessionExpiredError();
  if (response.status === 429) {
    // Two different 429s (src/api/main.py): the rate limiter means "slow
    // down", the daily budget means "come back tomorrow" — telling a
    // budget-exhausted user to wait a moment just gets them the same
    // error again the moment they retry.
    const message = data?.error === "daily token budget exhausted"
      ? "You've reached today's limit for asking questions. Try again tomorrow."
      : "You're sending requests too quickly. Wait a moment and try again.";
    return new ApiError(message, 429);
  }
  return new ApiError(data?.error || "Something went wrong.", response.status, data?.details);
}

export async function apiFetch(path, { method = "GET", token, body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }

  if (response.status === 204) return null;

  const data = await response.json().catch(() => null);

  if (!response.ok) throw errorFor(response, data, token);

  return data;
}

// A POST answered with text/event-stream. Errors before the stream reject as
// apiFetch's do, and so does a connection lost part-way; an abort is rethrown
// as the AbortError it is.
export async function apiStream(path, { token, body, signal, onEvent }) {
  const headers = { "Content-Type": "application/json", Accept: "text/event-stream" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { method: "POST", headers, body: JSON.stringify(body), signal });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError(UNREACHABLE, 0);
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw errorFor(response, data, token);
  }

  // EventSource can't POST or send a Bearer header, so the body is read by hand.
  const parser = createSseParser(onEvent);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError(UNREACHABLE, 0);
  } finally {
    // Frees the connection whichever way the loop ended; a finished stream
    // makes this a no-op, and a failed one can't fail it any further.
    reader.cancel().catch(() => {});
  }
  parser.push(decoder.decode());
  parser.end();
}
