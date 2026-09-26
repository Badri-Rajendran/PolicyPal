import { useCallback, useSyncExternalStore } from "react";

// Whether a CSS media query matches, following changes. False where
// matchMedia is missing (jsdom, very old browsers).
export function useMediaQuery(query) {
  const subscribe = useCallback(
    (onChange) => {
      if (!window.matchMedia) return () => {};
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );
  const snapshot = () => window.matchMedia?.(query).matches ?? false;
  return useSyncExternalStore(subscribe, snapshot, () => false);
}
