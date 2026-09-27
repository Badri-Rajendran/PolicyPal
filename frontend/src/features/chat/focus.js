// What Tab can reach in the chat's modal layers: the phone drawer and the
// Sources sheet.
export const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Tab and Shift+Tab stay inside a modal layer, wrapping at either end. Moved
// by hand, since focus can sit on an element that isn't itself in the tab
// order (a selected source card).
export function trapTab(event, container) {
  if (event.key !== "Tab") return;
  const focusable = [...container.querySelectorAll(FOCUSABLE)];
  if (focusable.length === 0) return;
  const current = document.activeElement;
  const position = (el) => current.compareDocumentPosition(el);
  const after = focusable.filter((el) => el !== current && position(el) & Node.DOCUMENT_POSITION_FOLLOWING);
  const before = focusable.filter((el) => el !== current && position(el) & Node.DOCUMENT_POSITION_PRECEDING);
  const next = event.shiftKey ? (before.at(-1) ?? focusable.at(-1)) : (after[0] ?? focusable[0]);
  event.preventDefault();
  next.focus();
}
