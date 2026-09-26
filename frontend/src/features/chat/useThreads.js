import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { SessionExpiredError } from "../../services/apiClient";
import * as chatService from "../../services/chatService";

export function useThreads() {
  const { token, expireSession } = useAuth();
  const [threads, setThreads] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");

  const fetchThreads = useCallback(() => {
    return chatService.listThreads(token).then(
      (data) => {
        setThreads(data);
        setStatus("ready");
      },
      (err) => {
        if (err instanceof SessionExpiredError) return expireSession();
        setError(err.message);
        setStatus("error");
      },
    );
  }, [token, expireSession]);

  useEffect(() => {
    fetchThreads();
  }, [fetchThreads]);

  const retry = useCallback(() => {
    setStatus("loading");
    setError("");
    fetchThreads();
  }, [fetchThreads]);

  async function createThread() {
    const thread = await chatService.createThread(token, null);
    setThreads((prev) => [thread, ...prev]);
    return thread;
  }

  async function removeThread(threadId) {
    await chatService.deleteThread(token, threadId);
    setThreads((prev) => prev.filter((t) => t.id !== threadId));
  }

  // A thread with new activity moves to the top, as the server orders it.
  function touchThread(threadId, title, updatedAt) {
    setThreads((prev) => {
      const thread = prev.find((t) => t.id === threadId);
      if (!thread) return prev;
      const touched = { ...thread, title: title ?? thread.title, ...(updatedAt ? { updated_at: updatedAt } : {}) };
      return [touched, ...prev.filter((t) => t.id !== threadId)];
    });
  }

  // Optimistic: the new title shows at once, and the old one comes back if the
  // server refuses it. A rename is not activity, so the thread doesn't move.
  async function renameThread(threadId, title) {
    const before = threads.find((t) => t.id === threadId);
    setThreads((prev) => prev.map((t) => (t.id === threadId ? { ...t, title } : t)));
    try {
      const saved = await chatService.renameThread(token, threadId, title);
      setThreads((prev) => prev.map((t) => (t.id === threadId ? saved : t)));
    } catch (err) {
      setThreads((prev) => prev.map((t) => (t.id === threadId ? before : t)));
      if (err instanceof SessionExpiredError) expireSession();
      throw err;
    }
  }

  return { threads, status, error, createThread, removeThread, renameThread, touchThread, retry };
}
