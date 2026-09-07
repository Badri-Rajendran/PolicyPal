import { apiFetch } from "./apiClient";

export function listThreads(token) {
  return apiFetch("/api/chat/threads", { token });
}

export function createThread(token, title) {
  return apiFetch("/api/chat/threads", { method: "POST", token, body: { title } });
}

export function deleteThread(token, threadId) {
  return apiFetch(`/api/chat/threads/${threadId}`, { method: "DELETE", token });
}

export function listMessages(token, threadId) {
  return apiFetch(`/api/chat/threads/${threadId}/messages`, { token });
}

export function sendMessage(token, threadId, content) {
  return apiFetch(`/api/chat/threads/${threadId}/messages`, {
    method: "POST",
    token,
    body: { content },
  });
}
