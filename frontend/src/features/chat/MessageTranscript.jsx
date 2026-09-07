import { useEffect, useRef } from "react";
import ThinkingIndicator from "../../components/ThinkingIndicator";
import EmptyState from "./EmptyState";
import MessageItem from "./MessageItem";

export default function MessageTranscript({ messages, status, isSending, onPrompt }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, isSending]);

  if (status === "loading") {
    return <div className="transcript transcript-loading">Loading conversation…</div>;
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
