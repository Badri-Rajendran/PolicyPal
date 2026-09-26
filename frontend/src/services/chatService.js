import { apiFetch, apiStream } from "./apiClient";

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

// The same send as sendMessage, answered as Server-Sent Events (ADR 0027).
export function streamMessage(token, threadId, content, { signal, onEvent }) {
  return apiStream(`/api/chat/threads/${threadId}/messages/stream`, { token, body: { content }, signal, onEvent });
}

export function renameThread(token, threadId, title) {
  return apiFetch(`/api/chat/threads/${threadId}`, { method: "PATCH", token, body: { title } });
}

// A cited passage, looked up by the MessageSource id the answer carries.
export function getSource(token, sourceId) {
  return apiFetch(`/api/chat/sources/${sourceId}`, { token });
}
