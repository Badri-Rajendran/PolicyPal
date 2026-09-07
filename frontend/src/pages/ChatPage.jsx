import ErrorBanner from "../components/ErrorBanner";
import ChatWindow from "../features/chat/ChatWindow";
import Sidebar from "../features/chat/Sidebar";
import "../features/chat/chat.css";
import { useThreads } from "../features/chat/useThreads";

export default function ChatPage() {
  const {
    threads,
    status,
    error,
    selectedThreadId,
    selectThread,
    createThread,
    removeThread,
    touchThread,
    retry,
  } = useThreads();

  const selectedThread = threads.find((t) => t.id === selectedThreadId);

  if (status === "error") {
    return (
      <div className="chat-shell chat-shell-error">
        <ErrorBanner>{error}</ErrorBanner>
        <button type="button" className="link" onClick={retry}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="chat-shell">
      <Sidebar
        threads={threads}
        status={status}
        selectedThreadId={selectedThreadId}
        onSelect={selectThread}
        onDelete={removeThread}
        onCreate={createThread}
      />
      <ChatWindow
        threadId={selectedThreadId}
        threadTitle={selectedThread?.title}
        onCreateThread={createThread}
        onThreadTitled={touchThread}
      />
    </div>
  );
}
