import { PanelLeft, Plus } from "lucide-react";
import { useId, useState } from "react";
import IconButton from "../../../components/IconButton";
import { matches } from "../../../utils/highlight";
import { modKey } from "../../../utils/shortcutKey";
import { groupThreads } from "../../../utils/threadGroups";
import AccountMenu from "./AccountMenu";
import ThreadListItem from "./ThreadListItem";
import ThreadSearch from "./ThreadSearch";
import "./sidebar.css";

function ThreadGroup({ label, children }) {
  const id = useId();
  return (
    <section className="group" aria-labelledby={id}>
      <h2 className="group-label" id={id}>
        {label}
      </h2>
      <ul className="group-list">{children}</ul>
    </section>
  );
}

function matchLabel(count) {
  if (count === 0) return null;
  return count === 1 ? "1 question matches" : `${count} questions match`;
}

// The thread list: new question, search, date groups and the account menu
// (Main.dc.html's aside).
export default function Sidebar({
  threads,
  status,
  selectedThreadId,
  onSelect,
  onCreate,
  onDelete,
  onRename,
  onHide,
  onSignOut,
}) {
  const [query, setQuery] = useState("");
  const searching = query.trim() !== "";
  const found = searching ? threads.filter((t) => matches(t.title || "New question", query)) : threads;
  const groups = searching
    ? found.length > 0
      ? [{ label: matchLabel(found.length), threads: found }]
      : []
    : groupThreads(threads);

  const item = (thread) => (
    <ThreadListItem
      key={thread.id}
      thread={thread}
      active={thread.id === selectedThreadId}
      query={query}
      onSelect={onSelect}
      onRename={onRename}
      onDelete={onDelete}
    />
  );

  return (
    <aside className="side" aria-label="Your questions">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          P
        </span>
        <span className="brand-name">PolicyPal</span>
        {onHide && (
          <IconButton label="Hide the sidebar" onClick={onHide}>
            <PanelLeft className="i" aria-hidden="true" />
          </IconButton>
        )}
      </div>
      <button type="button" className="newq" onClick={onCreate} aria-keyshortcuts="Control+K Meta+K">
        <Plus className="i" aria-hidden="true" />
        New question
        <span className="kbd" aria-hidden="true">
          {modKey()} K
        </span>
      </button>
      <ThreadSearch value={query} onChange={setQuery} />
      <nav className="threads" aria-label="Threads">
        {status === "loading" && <p className="side-hint">Loading your questions…</p>}
        {status === "ready" && threads.length === 0 && <p className="side-hint">Your questions will show up here.</p>}
        {searching && threads.length > 0 && found.length === 0 && <p className="side-hint">No questions match</p>}
        {groups.map((group) => (
          <ThreadGroup key={group.label} label={group.label}>
            {group.threads.map(item)}
          </ThreadGroup>
        ))}
      </nav>
      <AccountMenu onSignOut={onSignOut} />
    </aside>
  );
}
