import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { ApiError, SessionExpiredError } from "../../services/apiClient";
import * as chatService from "../../services/chatService";

const ANSWER_FAILED = "PolicyPal couldn't write an answer just now. Try again.";

let tempIdCounter = 0;

// A thread's messages, and the answer streaming into it (ADR 0027).
// `live` is the draft: { questionId, stages, notices, text } while an answer
// streams, else null. `done` replaces it with the saved answer.
export function useMessages(threadId, onThreadUpdated) {
  const { token, expireSession } = useAuth();
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState(threadId ? "loading" : "idle");
  const [error, setError] = useState("");
  const [loadedThreadId, setLoadedThreadId] = useState(threadId);
  const [sendError, setSendError] = useState("");
  const [live, setLive] = useState(null);
  // The question whose answer was stopped; cleared by the next send.
  const [stoppedId, setStoppedId] = useState(null);
  // The last answer to finish streaming here: its seals stamp in, and
  // history loaded later never does.
  const [finishedId, setFinishedId] = useState(null);
  // Bumped by retry to re-run the load effect for the same thread.
  const [reload, setReload] = useState(0);
  const controllerRef = useRef(null);

  if (threadId !== loadedThreadId) {
    setLoadedThreadId(threadId);
    setMessages([]);
    setError("");
    setSendError("");
    setLive(null);
    setStoppedId(null);
    // Coming back to a thread loads its history, which never stamps.
    setFinishedId(null);
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

  // An answer streaming into one thread is abandoned when another opens.
  useEffect(() => () => controllerRef.current?.abort(), [threadId]);

  const retry = useCallback(() => {
    setError("");
    setStatus("loading");
    setReload((n) => n + 1);
  }, []);

  async function send(content) {
    if (controllerRef.current) return; // one answer at a time

    const optimistic = { id: `temp-${tempIdCounter++}`, role: "user", content, created_at: new Date().toISOString() };
    let questionId = optimistic.id;
    let saved = false;
    let answered = false;
    const controller = new AbortController();
    controllerRef.current = controller;
    const update = (change) => setLive((current) => (current ? { ...current, ...change(current) } : current));

    setSendError("");
    setStoppedId(null);
    setMessages((prev) => [...prev, optimistic]);
    setLive({ questionId, stages: [], notices: [], text: "" });

    try {
      await chatService.streamMessage(token, threadId, content, {
        signal: controller.signal,
        onEvent: ({ event, data }) => {
          if (controller.signal.aborted) return;
          if (event === "user_message") {
            saved = true;
            questionId = data.message.id;
            setMessages((prev) => prev.map((m) => (m.id === optimistic.id ? data.message : m)));
            update(() => ({ questionId }));
          } else if (event === "stage") {
            update((l) => ({ stages: [...l.stages.filter((s) => s !== data.stage), data.stage] }));
          } else if (event === "notice") {
            update((l) => ({ notices: [...l.notices, data.text] }));
          } else if (event === "delta") {
            update((l) => ({ text: l.text + data.text }));
          } else if (event === "reset") {
            update(() => ({ text: "" }));
          } else if (event === "done") {
            answered = true;
            setMessages((prev) => [...prev, data.message]);
            setFinishedId(data.message.id);
            onThreadUpdated?.(data.thread);
          } else if (event === "error") {
            throw new ApiError(ANSWER_FAILED, 502);
          }
        },
      });
      // A stream that closed without `done` or `error` lost its answer.
      if (!answered && !controller.signal.aborted) throw new ApiError(ANSWER_FAILED, 502);
    } catch (err) {
      if (err?.name === "AbortError" || controller.signal.aborted) setStoppedId(questionId);
      else if (err instanceof SessionExpiredError) expireSession();
      else {
        if (!saved) setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
        setSendError(err.message);
      }
    } finally {
      // A newer send may already own the ref (after a thread switch).
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLive(null);
      }
    }
  }

  function stop() {
    controllerRef.current?.abort();
  }

  return {
    messages,
    status,
    error,
    live,
    isSending: live !== null,
    sendError,
    stoppedId,
    finishedId,
    send,
    stop,
    retry,
  };
}
