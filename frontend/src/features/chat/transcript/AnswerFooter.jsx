import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { formatSourceLabel } from "../../../utils/formatSource";
import { copyText, sourceNumbers } from "../../../utils/markers";

const COPY_LABELS = { idle: "Copy", copied: "Copied", failed: "Couldn't copy" };
const FEEDBACK_MS = 1600;

// Under an answer: a chip per cited document, numbered as its seals are, and Copy.
export default function AnswerFooter({ message, onOpenSource }) {
  const [copy, setCopy] = useState("idle");
  const sources = message.sources ?? [];
  const numbers = sourceNumbers(sources);
  // One chip per label: its first passage, which is what its seals open.
  const chips = [...numbers].map(([label, number]) => ({ label, number, source: sources.find((s) => s.source === label) }));

  // The feedback timer is outside React.
  useEffect(() => {
    if (copy === "idle") return undefined;
    const timer = setTimeout(() => setCopy("idle"), FEEDBACK_MS);
    return () => clearTimeout(timer);
  }, [copy]);

  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(copyText(message.content, sources, message.plans ?? []));
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  }

  return (
    <div className="afoot">
      {chips.map(({ label, number, source }) => (
        <button
          key={label}
          type="button"
          className="chip"
          aria-label={`Source ${number}, ${formatSourceLabel(label)}`}
          onClick={() => onOpenSource?.(source.id)}
        >
          <span className="seal" aria-hidden="true">
            {number}
          </span>
          <span className="t">{formatSourceLabel(label)}</span>
        </button>
      ))}
      <span className="sep" />
      <button type="button" className={copy === "copied" ? "tool done" : "tool"} aria-label="Copy answer" onClick={copyAnswer}>
        {copy === "copied" ? <Check className="i sm" aria-hidden="true" /> : <Copy className="i sm" aria-hidden="true" />}
        <span aria-live="polite">{COPY_LABELS[copy]}</span>
      </button>
    </div>
  );
}
