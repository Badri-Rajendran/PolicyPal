import { fireEvent, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useShortcuts } from "./useShortcuts";

function setup() {
  const handlers = { onNewQuestion: vi.fn(), onFocusComposer: vi.fn(), onEscape: vi.fn() };
  const view = renderHook(() => useShortcuts(handlers));
  return { ...handlers, ...view };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("useShortcuts", () => {
  it("Ctrl+K and ⌘K start a new question, instead of the browser's own", () => {
    const { onNewQuestion } = setup();
    const ctrl = fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const meta = fireEvent.keyDown(window, { key: "K", metaKey: true });
    expect(onNewQuestion).toHaveBeenCalledTimes(2);
    expect(ctrl).toBe(false); // default prevented
    expect(meta).toBe(false);
  });

  it("Ctrl+K works even while typing", () => {
    const { onNewQuestion } = setup();
    const input = document.createElement("textarea");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "k", ctrlKey: true });
    expect(onNewQuestion).toHaveBeenCalledOnce();
  });

  it("/ focuses the composer", () => {
    const { onFocusComposer } = setup();
    const notTyped = fireEvent.keyDown(document.body, { key: "/" });
    expect(onFocusComposer).toHaveBeenCalledOnce();
    expect(notTyped).toBe(false);
  });

  it.each(["input", "textarea", "select"])("/ is left alone while typing in a %s", (tag) => {
    const { onFocusComposer } = setup();
    const field = document.createElement(tag);
    document.body.appendChild(field);
    fireEvent.keyDown(field, { key: "/" });
    expect(onFocusComposer).not.toHaveBeenCalled();
  });

  it("Escape calls onEscape", () => {
    const { onEscape } = setup();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onEscape).toHaveBeenCalledOnce();
  });

  it("stops listening when unmounted", () => {
    const { onEscape, unmount } = setup();
    unmount();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onEscape).not.toHaveBeenCalled();
  });

  it("ignores other keys", () => {
    const { onNewQuestion, onFocusComposer, onEscape } = setup();
    fireEvent.keyDown(window, { key: "k" });
    fireEvent.keyDown(window, { key: "a", ctrlKey: true });
    expect(onNewQuestion).not.toHaveBeenCalled();
    expect(onFocusComposer).not.toHaveBeenCalled();
    expect(onEscape).not.toHaveBeenCalled();
  });
});
