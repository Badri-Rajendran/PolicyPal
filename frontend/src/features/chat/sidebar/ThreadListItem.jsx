import { Ellipsis, Pencil, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import Button from "../../../components/Button";
import IconButton from "../../../components/IconButton";
import Menu from "../../../components/Menu";
import { highlight } from "../../../utils/highlight";

const UNTITLED = "New question";

function Title({ text, query }) {
  return highlight(text, query).map((part, i) => (part.match ? <mark key={i}>{part.text}</mark> : part.text));
}

function RenameField({ title, onSave, onCancel }) {
  const [value, setValue] = useState(title);
  const [error, setError] = useState("");
  const hintId = useId();

  function onKeyDown(event) {
    if (event.key === "Escape") {
      // Stopped here, so the page's Esc shortcut isn't also run.
      event.preventDefault();
      event.stopPropagation();
      onCancel();
    } else if (event.key === "Enter") {
      event.preventDefault();
      const trimmed = value.trim();
      if (!trimmed) setError("Enter a name");
      else onSave(trimmed);
    }
  }

  return (
    <li className="thread-edit">
      <div className="thread renaming">
        <input
          aria-label="Thread name"
          value={value}
          maxLength={200}
          autoFocus
          aria-invalid={Boolean(error)}
          aria-describedby={hintId}
          onChange={(event) => {
            setValue(event.target.value);
            setError("");
          }}
          onKeyDown={onKeyDown}
          onBlur={onCancel}
        />
      </div>
      <div id={hintId} className={error ? "rename-hint bad" : "rename-hint muted"}>
        {error || "Enter to save, Esc to cancel"}
      </div>
    </li>
  );
}

function DeleteConfirm({ title, onDelete, onCancel }) {
  return (
    <li>
      <div
        className="thread confirm"
        role="group"
        aria-label={`Delete ${title}?`}
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          event.preventDefault();
          event.stopPropagation();
          onCancel();
        }}
      >
        <span className="confirm-text">
          Delete <strong>{title}</strong> and its answers?
        </span>
        <span className="confirm-actions">
          <Button variant="danger" className="sm" type="button" onClick={onDelete}>
            Delete
          </Button>
          <Button variant="ghost" className="sm" type="button" autoFocus onClick={onCancel}>
            Keep it
          </Button>
        </span>
      </div>
    </li>
  );
}

// One thread in the sidebar. Its ⋯ menu renames it inline or asks, inline,
// before deleting it (SidebarRename.dc.html).
export default function ThreadListItem({ thread, active, query, onSelect, onRename, onDelete }) {
  // "idle", "renaming" or "confirming"; `refocus` puts focus back on the
  // title after an edit or a confirmation closes.
  const [mode, setMode] = useState({ name: "idle", refocus: false });
  const title = thread.title || UNTITLED;
  const back = () => setMode({ name: "idle", refocus: true });

  if (mode.name === "renaming") {
    return (
      <RenameField
        title={thread.title ?? ""}
        onCancel={back}
        onSave={(next) => {
          back();
          if (next !== thread.title) onRename(thread.id, next);
        }}
      />
    );
  }

  if (mode.name === "confirming") {
    return <DeleteConfirm title={title} onCancel={back} onDelete={() => onDelete(thread.id)} />;
  }

  return (
    <li className={active ? "thread active" : "thread"}>
      <button
        type="button"
        className="thread-title"
        aria-current={active ? "page" : undefined}
        autoFocus={mode.refocus}
        onClick={() => onSelect(thread.id)}
      >
        <Title text={title} query={query} />
      </button>
      <Menu
        label={`Options for ${title}`}
        trigger={(props) => (
          <IconButton label={`Options for ${title}`} {...props}>
            <Ellipsis className="i sm" aria-hidden="true" />
          </IconButton>
        )}
        items={[
          { label: "Rename", icon: Pencil, onSelect: () => setMode({ name: "renaming", refocus: false }) },
          { label: "Delete", icon: Trash2, danger: true, onSelect: () => setMode({ name: "confirming", refocus: false }) },
        ]}
      />
    </li>
  );
}
