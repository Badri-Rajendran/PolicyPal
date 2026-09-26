// The modifier the Ctrl/⌘K shortcut uses on this device, as the UI names it.
export function modKey() {
  return globalThis.navigator?.platform?.includes("Mac") ? "⌘" : "Ctrl";
}
