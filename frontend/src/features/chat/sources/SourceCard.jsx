import { ExternalLink } from "lucide-react";
import { formatSourceLabel } from "../../../utils/formatSource";
import { safeUrl } from "../../../utils/safeUrl";
import { useSource } from "./useSource";

const LINK_TEXT = { sbc: "Carrier's PDF", wikipedia: "Read on Wikipedia" };
const GONE = "This passage has changed since the answer and can't be shown.";
const MAY_HAVE_CHANGED = "This passage may have changed since the answer.";

function httpsOnly(url) {
  const safe = url ? safeUrl(url) : null;
  return safe?.startsWith("https:") ? safe : null;
}

function NewTabLink({ href, children, className }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}

// An SBC row reads "Urgent care | $50 copay/visit | …": the bars are muted.
function Quote({ text }) {
  const parts = text.split(" | ");
  return (
    <p className="quote">
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 && <span className="muted"> | </span>}
          {part}
        </span>
      ))}
    </p>
  );
}

function Passage({ passage, relevance }) {
  const shown = passage.status === "ok" || passage.status === "unverified";
  const href = httpsOnly(passage.url);
  const license = passage.kind === "wikipedia" && passage.license ? passage.license : null;
  const licenseHref = httpsOnly(license?.url);
  const percent = Math.round(relevance * 100);

  return (
    <>
      {shown && passage.quote && <Quote text={passage.quote} />}
      {passage.status === "unverified" && <p className="gone">{MAY_HAVE_CHANGED}</p>}
      {!shown && <p className="gone">{GONE}</p>}
      <div className="src-meta">
        <span className="meter" role="img" aria-label={`${percent}% match`}>
          <i style={{ width: `${percent}%` }} />
        </span>
        <span aria-hidden="true">{percent}% match</span>
        {href && (
          <NewTabLink href={href}>
            {LINK_TEXT[passage.kind] ?? "Open the source"}
            <ExternalLink className="i sm" aria-hidden="true" />
          </NewTabLink>
        )}
      </div>
      {shown && license && (
        <p className="credit muted">
          Text from the Wikipedia article “{passage.title}”, by its contributors, under{" "}
          {licenseHref ? (
            // Labelled rather than given hidden text, so the credit reads as one sentence.
            <a href={licenseHref} target="_blank" rel="noopener noreferrer" aria-label={`${license.name} (opens in a new tab)`}>
              {license.name}
            </a>
          ) : (
            license.name
          )}
          .
        </p>
      )}
    </>
  );
}

// One cited source, its passage fetched when the card is first shown.
export default function SourceCard({ source, number, selected = false, hovered = false, onSelect, cardRef }) {
  const { status, passage, retry } = useSource(source.id);
  const title = passage?.title ?? formatSourceLabel(source.source);
  const kind = passage ? [passage.document, passage.section].filter(Boolean).join(". ") : "";
  const classes = ["src", selected && "sel", hovered && "hover"].filter(Boolean).join(" ");

  return (
    // The whole card selects it for a pointer; the seals in the answer are the keyboard's way here.
    <article ref={cardRef} className={classes} aria-current={selected ? "true" : undefined} tabIndex={-1} onClick={() => onSelect?.(source.id)}>
      <div className="src-top">
        <span className="seal" aria-hidden="true">
          {number}
        </span>
        <div>
          <div className="src-title">
            <span className="visually-hidden">Source {number}: </span>
            {title}
          </div>
          {kind && <div className="src-kind">{kind}</div>}
        </div>
      </div>
      {status === "loading" && <p className="gone">Loading the passage…</p>}
      {status === "error" && (
        <p className="gone">
          This source couldn't be loaded.{" "}
          <button
            type="button"
            className="link"
            onClick={(event) => {
              event.stopPropagation();
              retry();
            }}
          >
            Try again
          </button>
        </p>
      )}
      {status === "ready" && <Passage passage={passage} relevance={source.relevance} />}
    </article>
  );
}
