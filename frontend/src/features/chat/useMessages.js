import { useEffect, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import * as chatService from "../../services/chatService";

let tempIdCounter = 0;

export function useMessages(threadId, onThreadTitled) {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState(threadId ? "loading" : "idle");
  const [loadedThreadId, setLoadedThreadId] = useState(threadId);
  const [sendError, setSendError] = useState("");
  const [isSending, setIsSending] = useState(false);

  if (threadId !== loadedThreadId) {
    setLoadedThreadId(threadId);
    setMessages([]);
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
      () => {
        if (!ignore) setStatus("error");
      },
    );

    return () => {
      ignore = true;
    };
  }, [threadId, token]);

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
      const data = await chatService.sendMessage(token, threadId, content);
      setMessages((prev) => [...prev, { ...data.message, sources: data.sources }]);
      if (isFirstMessage) onThreadTitled?.(threadId, content.slice(0, 80));
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticMessage.id));
      setSendError(err.message);
    } finally {
      setIsSending(false);
    }
  }

  return { messages, status, isSending, sendError, send };
}
