import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { SessionExpiredError } from "../../services/apiClient";
import * as chatService from "../../services/chatService";

let tempIdCounter = 0;

export function useMessages(threadId, onThreadTitled) {
  const { token, expireSession } = useAuth();
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState(threadId ? "loading" : "idle");
  const [error, setError] = useState("");
  const [loadedThreadId, setLoadedThreadId] = useState(threadId);
  const [sendError, setSendError] = useState("");
  const [isSending, setIsSending] = useState(false);
  // Bumped by retry to re-run the load effect for the same thread.
  const [reload, setReload] = useState(0);

  if (threadId !== loadedThreadId) {
    setLoadedThreadId(threadId);
    setMessages([]);
    setError("");
    setStatus(threadId ? "loading" : "idle");
  }

  useEffect(() => {
    if (!threadId) return;

    let ignore = false;
    chatService.listMessages(token, threadId).then(
      (data) => {
        if (!ignore) {
          // A send kicked off for this same thread (e.g. the first message,
          // fired the moment the thread was created) may already have added
          // an optimistic message by the time this history fetch resolves.
          // Never let a slower-starting-but-faster-finishing GET erase it.
          setMessages((prev) => (prev.length > 0 ? prev : data));
          setStatus("ready");
        }
      },
      (err) => {
        if (ignore) return;
        if (err instanceof SessionExpiredError) return expireSession();
        setError(err.message);
        setStatus("error");
      },
    );

    return () => {
      ignore = true;
    };
  }, [threadId, token, expireSession, reload]);

  const retry = useCallback(() => {
    setError("");
    setStatus("loading");
    setReload((n) => n + 1);
  }, []);

  async function send(content) {
    const isFirstMessage = messages.length === 0;
    const optimisticMessage = {
      id: `temp-${tempIdCounter++}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };

    setSendError("");
    setMessages((prev) => [...prev, optimisticMessage]);
    setIsSending(true);

    try {
      const message = await chatService.sendMessage(token, threadId, content);
      setMessages((prev) => [...prev, message]);
      if (isFirstMessage) onThreadTitled?.(threadId, content.slice(0, 80));
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticMessage.id));
      if (err instanceof SessionExpiredError) expireSession();
      else setSendError(err.message);
    } finally {
      setIsSending(false);
    }
  }

  return { messages, status, error, isSending, sendError, send, retry };
}
