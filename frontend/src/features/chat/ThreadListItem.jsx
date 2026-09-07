export default function ThreadListItem({ thread, active, onSelect, onDelete }) {
  return (
    <li className={`thread-item ${active ? "is-active" : ""}`}>
      <button type="button" className="thread-item-select" onClick={() => onSelect(thread.id)}>
        {thread.title || "New question"}
      </button>
      <button
        type="button"
        className="thread-item-delete"
        aria-label={`Delete "${thread.title || "New question"}"`}
        onClick={() => onDelete(thread.id)}
      >
        ×
      </button>
    </li>
  );
}
