import Button from "../../components/Button";
import { useAuth } from "../../hooks/useAuth";
import ThreadListItem from "./ThreadListItem";

export default function Sidebar({ threads, status, selectedThreadId, onSelect, onDelete, onCreate }) {
  const { user, logout } = useAuth();

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>PolicyPal</h1>
        <Button variant="ghost" onClick={onCreate}>
          New question
        </Button>
      </div>

      {status === "loading" && <p className="sidebar-hint">Loading your questions…</p>}
      {status === "ready" && threads.length === 0 && (
        <p className="sidebar-hint">Your questions will show up here.</p>
      )}

      <ul className="thread-list">
        {threads.map((thread) => (
          <ThreadListItem
            key={thread.id}
            thread={thread}
            active={thread.id === selectedThreadId}
            onSelect={onSelect}
            onDelete={onDelete}
          />
        ))}
      </ul>

      <div className="sidebar-footer">
        <span className="sidebar-email">{user?.email}</span>
        <button type="button" className="link" onClick={logout}>
          Sign out
        </button>
      </div>
    </aside>
  );
}
