import { useNavigate, useParams } from "react-router";
import ErrorBanner from "../components/ErrorBanner";
import ChatWindow from "../features/chat/ChatWindow";
import Sidebar from "../features/chat/Sidebar";
import ProfileNudge from "../features/profile/ProfileNudge";
import "../features/chat/chat.css";
import "../features/plans/plans.css";
import "../features/profile/profile.css";
import { useThreads } from "../features/chat/useThreads";
import { useAuth } from "../hooks/useAuth";

export default function ChatPage() {
  const { threadId } = useParams();
  const navigate = useNavigate();
  const { threads, status, error, createThread, removeThread, touchThread, retry } = useThreads();
  const { user } = useAuth();

  const selectedThread = threads.find((t) => t.id === threadId);

  async function startThread() {
    const thread = await createThread();
    navigate(`/chat/${thread.id}`);
    return thread;
  }

  async function deleteThread(id) {
    await removeThread(id);
    if (id === threadId) navigate("/chat", { replace: true });
  }

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
        selectedThreadId={threadId ?? null}
        onSelect={(id) => navigate(`/chat/${id}`)}
        onDelete={deleteThread}
        onCreate={startThread}
      />
      <ChatWindow
        threadId={threadId ?? null}
        threadTitle={selectedThread?.title}
        // Strictly false: a session stored before profiles existed has no flag, and is not nagged on a guess.
        notice={user?.profile_complete === false ? <ProfileNudge /> : null}
        onCreateThread={startThread}
        onThreadTitled={touchThread}
      />
    </div>
  );
}
