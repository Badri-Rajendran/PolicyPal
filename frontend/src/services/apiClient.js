const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details;
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
    if (response.status === 429) {
      throw new ApiError("You're sending requests too quickly. Wait a moment and try again.", 429);
    }
    throw new ApiError(data?.error || "Something went wrong.", response.status, data?.details);
  }

  return data;
}
