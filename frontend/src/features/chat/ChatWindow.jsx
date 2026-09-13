import { useEffect, useRef, useState } from "react";
import ErrorBanner from "../../components/ErrorBanner";
import Composer from "./Composer";
import MessageTranscript from "./MessageTranscript";
import { useMessages } from "./useMessages";

export default function ChatWindow({ threadId, threadTitle, onCreateThread, onThreadTitled }) {
  const { messages, status, isSending, sendError, send } = useMessages(threadId, onThreadTitled);
  const [draft, setDraft] = useState("");
  const [draftThreadId, setDraftThreadId] = useState(threadId);
  const pendingFirstMessage = useRef(null);

  if (threadId !== draftThreadId) {
    setDraftThreadId(threadId);
    setDraft("");
  }

  useEffect(() => {
    if (threadId && pendingFirstMessage.current) {
      const content = pendingFirstMessage.current;
      pendingFirstMessage.current = null;
      send(content);
    }
    // Runs once per new thread id, using whichever `send` closure this render created.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  async function handleSubmit(content) {
    setDraft("");
    if (!threadId) {
      pendingFirstMessage.current = content;
      await onCreateThread();
    } else {
      send(content);
    }
  }

  return (
    <section className="chat-window">
      <header className="chat-window-header">
        <h2>{threadTitle || "New question"}</h2>
      </header>

      <MessageTranscript messages={messages} status={status} isSending={isSending} onPrompt={setDraft} />

      <div className="composer-area">
        <ErrorBanner>{sendError}</ErrorBanner>
        <Composer value={draft} onChange={setDraft} onSubmit={() => handleSubmit(draft)} disabled={isSending} />
      </div>
    </section>
  );
}
