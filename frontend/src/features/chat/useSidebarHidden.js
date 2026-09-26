import { useState } from "react";

const KEY = "policypal.sidebar";

// localStorage holds only whether the sidebar is hidden, per browser (spec §4.4).
function read() {
  try {
    return localStorage.getItem(KEY) === "hidden";
  } catch {
    return false;
  }
}

function store(hidden) {
  try {
    if (hidden) localStorage.setItem(KEY, "hidden");
    else localStorage.removeItem(KEY);
  } catch {
    // Storage unavailable: the choice holds for this page only.
  }
}

// Whether the desktop sidebar is collapsed, shared by the chat and profile pages.
export function useSidebarHidden() {
  const [hidden, setHiddenState] = useState(read);

  function setHidden(next) {
    store(next);
    setHiddenState(next);
  }

  return [hidden, setHidden];
}
