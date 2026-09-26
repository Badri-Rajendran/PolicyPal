import { useEffect, useEffectEvent } from "react";

const TYPING = "input, textarea, select, [contenteditable='true']";

// Ctrl/⌘K new question, "/" to type, Esc to stop or close (spec §4.3).
// Menus, the sheet and inline editors stop their own Esc first.
export function useShortcuts({ onNewQuestion, onFocusComposer, onEscape }) {
  const onKeyDown = useEffectEvent((event) => {
    const typing = event.target instanceof Element && event.target.closest(TYPING);
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      onNewQuestion?.();
    } else if (event.key === "Escape") {
      onEscape?.(event);
    } else if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      onFocusComposer?.();
    }
  });

  // The keyboard is outside React: one window listener while mounted.
  useEffect(() => {
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
