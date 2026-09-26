import { ArrowUp, Square } from "lucide-react";
import { useImperativeHandle, useLayoutEffect, useRef } from "react";

const MAX_HEIGHT = 200;

// The question box (Main.dc.html's dock): Enter sends, Shift+Enter adds a
// line, and while an answer streams the send button becomes Stop.
export default function Composer({ ref, value, onChange, onSubmit, onStop, isSending, placeholder }) {
  const textareaRef = useRef(null);
  useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }), []);

  // Grows with its text, up to a limit; the height is measured from the DOM.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  function submit() {
    const content = value.trim();
    if (content && !isSending) onSubmit(content);
  }

  function onKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <>
      <form
        className="composer"
        aria-label="Ask a question"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          aria-label="Your question"
          placeholder={placeholder}
          value={value}
          disabled={isSending}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="crow">
          <span className="hint">
            {isSending ? "Press Esc or Stop to cancel this answer" : "Enter to send, Shift+Enter for a new line"}
          </span>
          {isSending ? (
            <button type="button" className="send stop" aria-label="Stop answering" onClick={onStop}>
              <Square className="i sm" aria-hidden="true" />
            </button>
          ) : (
            <button type="submit" className="send" aria-label="Send" disabled={!value.trim()}>
              <ArrowUp className="i" aria-hidden="true" />
            </button>
          )}
        </div>
      </form>
      <p className="privacy">
        Questions and the passages found for them are sent to OpenAI to write answers. Don't include personal details.
      </p>
    </>
  );
}
