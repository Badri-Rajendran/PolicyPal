import { FileText, Menu as MenuIcon, PanelLeft, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import IconButton from "../../components/IconButton";

function TitleEditor({ title, onSave, onCancel }) {
  const [value, setValue] = useState(title);
  const [invalid, setInvalid] = useState(false);

  function onKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation(); // not also the page's Esc
      onCancel();
    } else if (event.key === "Enter") {
      event.preventDefault();
      const trimmed = value.trim();
      if (!trimmed) setInvalid(true);
      else onSave(trimmed);
    }
  }

  return (
    <input
      className="title-input"
      aria-label="Thread name"
      value={value}
      maxLength={200}
      autoFocus
      aria-invalid={invalid}
      onChange={(event) => {
        setValue(event.target.value);
        setInvalid(false);
      }}
      onKeyDown={onKeyDown}
      onBlur={onCancel}
    />
  );
}

// The chat's top bar (Main.dc.html; Mobile.dc.html when `compact`): the
// thread's title, renamed in place, and the Sources toggle.
export default function ChatHeader({
  title,
  onRename,
  sourcesCount = 0,
  sourcesOpen = false,
  onToggleSources,
  sidebarHidden = false,
  onShowSidebar,
  compact = false,
  onOpenDrawer,
  onNewQuestion,
}) {
  const [editing, setEditing] = useState({ on: false, refocus: false });
  const done = () => setEditing({ on: false, refocus: true });

  let heading;
  if (editing.on) {
    heading = (
      <TitleEditor
        title={title}
        onCancel={done}
        onSave={(next) => {
          done();
          if (next !== title) onRename(next);
        }}
      />
    );
  } else if (onRename) {
    heading = (
      <button
        type="button"
        className="title-btn"
        aria-label={`Rename this thread: ${title}`}
        autoFocus={editing.refocus}
        onClick={() => setEditing({ on: true, refocus: false })}
      >
        <span className="title-text">{title}</span>
        <Pencil className="i sm" aria-hidden="true" />
      </button>
    );
  } else {
    heading = <span className="title-btn title-static">{title}</span>;
  }

  return (
    <header className={compact ? "topbar compact" : "topbar"}>
      {compact && (
        <IconButton label="Open your questions" onClick={onOpenDrawer}>
          <MenuIcon className="i" aria-hidden="true" />
        </IconButton>
      )}
      {!compact && sidebarHidden && (
        <>
          <IconButton label="Show the sidebar" onClick={onShowSidebar}>
            <PanelLeft className="i" aria-hidden="true" />
          </IconButton>
          <span className="brand-mark small" aria-hidden="true">
            P
          </span>
        </>
      )}
      {heading}
      <span className="spacer" />
      {compact ? (
        <IconButton label="New question" onClick={onNewQuestion}>
          <Plus className="i" aria-hidden="true" />
        </IconButton>
      ) : (
        <button
          type="button"
          className={sourcesOpen ? "pill-btn on" : "pill-btn"}
          aria-pressed={sourcesOpen}
          disabled={sourcesCount === 0}
          onClick={onToggleSources}
        >
          <FileText className="i sm" aria-hidden="true" />
          Sources
          {sourcesCount > 0 && (
            <>
              {" "}
              <span className="count">{sourcesCount}</span>
            </>
          )}
        </button>
      )}
    </header>
  );
}
