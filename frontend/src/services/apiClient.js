// 127.0.0.1, not localhost: macOS AirPlay Receiver listens on *:5000, and
// localhost resolving to ::1 reaches it instead of Flask, which binds IPv4.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5000";

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
    throw new ApiError("Can't reach PolicyPal right now. Check your connection and try again.", 0);
  }

  if (response.status === 204) return null;

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    // Only a request that carried a token can have a dead one. A 401 from
    // login means the credentials were wrong, which is a different message.
    // flask-jwt-extended answers 401 for an expired token and 422 for an
    // unusable one, both under "msg"; the API's own 422 carries "error"
    // instead, so a validation failure is never mistaken for a dead session.
    const rejectedTheToken = response.status === 401 || (response.status === 422 && data?.msg);
    if (rejectedTheToken && token) {
      throw new SessionExpiredError();
    }
    if (response.status === 429) {
      throw new ApiError("You're sending requests too quickly. Wait a moment and try again.", 429);
    }
    throw new ApiError(data?.error || "Something went wrong.", response.status, data?.details);
  }

  return data;
}
