import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import * as chatService from "../../services/chatService";

export function useThreads() {
  const { token } = useAuth();
  const [threads, setThreads] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [selectedThreadId, setSelectedThreadId] = useState(null);

  const fetchThreads = useCallback(() => {
    return chatService.listThreads(token).then(
      (data) => {
        setThreads(data);
        setStatus("ready");
      },
      (err) => {
        setError(err.message);
        setStatus("error");
      },
    );
  }, [token]);

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
    setSelectedThreadId(thread.id);
    return thread;
  }

  async function removeThread(threadId) {
    await chatService.deleteThread(token, threadId);
    setThreads((prev) => prev.filter((t) => t.id !== threadId));
    setSelectedThreadId((current) => (current === threadId ? null : current));
  }

  function touchThread(threadId, title) {
    setThreads((prev) => {
      const updated = prev.map((t) => (t.id === threadId ? { ...t, title: title ?? t.title } : t));
      const thread = updated.find((t) => t.id === threadId);
      return [thread, ...updated.filter((t) => t.id !== threadId)];
    });
  }

  return {
    threads,
    status,
    error,
    selectedThreadId,
    selectThread: setSelectedThreadId,
    createThread,
    removeThread,
    touchThread,
    retry,
  };
}
