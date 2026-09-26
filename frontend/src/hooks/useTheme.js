import { useCallback, useState } from "react";

const KEY = "policypal.theme";
const CHOICES = ["system", "light", "dark"];

// localStorage, unlike the session: a theme is a device preference, not a secret.
export function readTheme() {
  try {
    const stored = localStorage.getItem(KEY);
    return CHOICES.includes(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

// System removes the attribute, so prefers-color-scheme decides (index.css).
export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "light" || theme === "dark") root.dataset.theme = theme;
  else delete root.dataset.theme;
}

export function useTheme() {
  const [theme, setThemeState] = useState(readTheme);

  const setTheme = useCallback((next) => {
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      // Storage unavailable: the choice holds for this page only.
    }
    applyTheme(next);
    setThemeState(next);
  }, []);

  return { theme, setTheme };
}
