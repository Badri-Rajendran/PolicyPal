import { motion } from "motion/react";
import { createContext, use, useEffect, useId, useRef, useState } from "react";

// Everything the arrow keys move between, including a theme radio group.
const ITEMS = '[role="menuitem"], [role="radio"]';

const CloseContext = createContext(() => {});

// One choice in a menu. Selecting it closes the menu first, returning focus to
// the trigger, so whatever the choice opens can take focus after.
export function MenuItem({ onSelect, danger = false, icon: Icon, children }) {
  const close = use(CloseContext);
  return (
    <button
      type="button"
      role="menuitem"
      tabIndex={-1}
      className={danger ? "danger" : undefined}
      onClick={() => {
        close();
        onSelect?.();
      }}
    >
      {Icon && <Icon className="i sm" aria-hidden="true" />}
      {children}
    </button>
  );
}

// A menu button (WAI-ARIA APG): the trigger opens a list of items; arrows,
// Home and End move, Enter or Space select, Esc or a click outside closes.
// Rendered in place under its trigger, not in a portal.
export default function Menu({ label, trigger, items = [], children, placement = "below", className = "" }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const id = useId();

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  // Focus and outside clicks are the DOM's, not React state.
  useEffect(() => {
    if (!open) return undefined;
    menuRef.current?.querySelector(ITEMS)?.focus();
    function onMouseDown(event) {
      if (menuRef.current?.contains(event.target) || triggerRef.current?.contains(event.target)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  function onKeyDown(event) {
    const all = [...menuRef.current.querySelectorAll(ITEMS)];
    const index = all.indexOf(document.activeElement);
    let next = null;
    if (event.key === "ArrowDown") next = all[(index + 1) % all.length];
    else if (event.key === "ArrowUp") next = all[(index - 1 + all.length) % all.length];
    else if (event.key === "Home") next = all[0];
    else if (event.key === "End") next = all.at(-1);
    else if (event.key === "Escape") {
      // Stopped here, so the page's Esc shortcut doesn't also stop an answer.
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    } else if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (next) {
      event.preventDefault();
      next.focus();
    }
  }

  return (
    <div className={["menu-anchor", className].filter(Boolean).join(" ")}>
      {trigger({
        ref: triggerRef,
        "aria-haspopup": "menu",
        "aria-expanded": open,
        "aria-controls": open ? id : undefined,
        onClick: () => setOpen((current) => !current),
      })}
      {open && (
        <motion.div
          ref={menuRef}
          id={id}
          role="menu"
          aria-label={label}
          className={`menu ${placement}`}
          onKeyDown={onKeyDown}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.12 }}
        >
          <CloseContext value={close}>
            {items.map((item) => (
              <MenuItem key={item.label} {...item}>
                {item.label}
              </MenuItem>
            ))}
            {children}
          </CloseContext>
        </motion.div>
      )}
    </div>
  );
}
