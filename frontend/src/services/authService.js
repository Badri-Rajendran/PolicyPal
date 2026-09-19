import { apiFetch } from "./apiClient";

export function register(email, password, profile) {
  return apiFetch("/api/auth/register", { method: "POST", body: { email, password, ...profile } });
}

export function login(email, password) {
  return apiFetch("/api/auth/login", { method: "POST", body: { email, password } });
}

export function fetchCurrentUser(token) {
  return apiFetch("/api/auth/me", { token });
}
