import { apiFetch } from "./apiClient";

export function getProfile(token) {
  return apiFetch("/api/profile", { token });
}

export function updateProfile(token, profile) {
  return apiFetch("/api/profile", { method: "PUT", token, body: profile });
}

export function lookupCounties(zipCode) {
  return apiFetch(`/api/counties?zip=${encodeURIComponent(zipCode)}`);
}
