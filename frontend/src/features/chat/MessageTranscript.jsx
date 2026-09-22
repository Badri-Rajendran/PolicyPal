import { useEffect, useRef } from "react";
import ErrorBanner from "../../components/ErrorBanner";
import ThinkingIndicator from "../../components/ThinkingIndicator";
import EmptyState from "./EmptyState";
import MessageItem from "./MessageItem";

export default function MessageTranscript({ messages, status, error, isSending, onPrompt, onRetry }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, isSending]);

  if (status === "loading") {
    return <div className="transcript transcript-loading">Loading conversation…</div>;
  }

  // Before the empty check: a thread that failed to load has no messages either,
  // and saying "ask about your policy" would hide that its history is missing.
  if (status === "error") {
    return (
      <div className="transcript transcript-error">
        <ErrorBanner>{error || "This conversation couldn't be loaded."}</ErrorBanner>
        <button type="button" className="link" onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="transcript">
        <EmptyState onPrompt={onPrompt} />
      </div>
    );
  }

  return (
    <div className="transcript">
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}
      {isSending && <ThinkingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
