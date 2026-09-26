import { Info } from "lucide-react";
import { linkify } from "../../../utils/linkify";

// A server-written notice before an answer (ADR 0024, 0026). Plain text, with
// its https links made links.
export default function Notice({ children }) {
  return (
    <div className="notice" role="note">
      <Info className="i" aria-hidden="true" />
      <span>
        {linkify(children).map((part, i) =>
          part.href ? (
            <a key={i} href={part.href} target="_blank" rel="noopener noreferrer">
              {part.text}
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          ) : (
            part.text
          ),
        )}
      </span>
    </div>
  );
}
