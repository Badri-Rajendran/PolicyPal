import { createContext, use } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { remarkMarkers } from "../../../utils/markers";
import { safeUrl } from "../../../utils/safeUrl";
import PlanRef from "./PlanRef";
import Seal from "./Seal";

// What the markdown components need from the answer they're in. Passed by
// context, so the components below keep one identity: react-markdown would
// otherwise remount every seal on each render, and replay the stamp.
const AnswerContext = createContext(null);

// Only https links, and only what safeUrl accepts; anything else loses its href.
function httpsOnly(url) {
  const safe = safeUrl(url);
  return safe?.startsWith("https:") ? safe : null;
}

function Link({ href, children }) {
  if (!href) return <>{children}</>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}

// An image would load from wherever the model pointed; its description is enough.
function ImageText({ alt }) {
  return alt ? <>{alt}</> : null;
}

// The question is the exchange's h2, so an answer's headings sit below it.
const Heading3 = ({ children }) => <h3>{children}</h3>;
const Heading4 = ({ children }) => <h4>{children}</h4>;
const Heading5 = ({ children }) => <h5>{children}</h5>;

function Table({ children }) {
  return (
    <div className="md-table-scroll" tabIndex={0}>
      <table>{children}</table>
    </div>
  );
}

function SealMarker({ number, label, index }) {
  const { message, stamp, selectedSourceId, onOpenSource, onHoverSource } = use(AnswerContext);
  const sourceId = message.sources?.find((s) => s.source === label)?.id ?? null;
  return (
    <Seal
      number={Number(number)}
      index={Number(index) || 0}
      stamp={stamp}
      selected={sourceId !== null && sourceId === selectedSourceId}
      onClick={() => onOpenSource?.(sourceId)}
      onHover={(on) => onHoverSource?.(on ? sourceId : null)}
    />
  );
}

function PlanMarker({ position, planId, children }) {
  const { message } = use(AnswerContext);
  const at = Number(position);
  const name = message.plans?.[at - 1]?.name ?? String(planId);
  return (
    <PlanRef position={at} messageId={message.id} name={name}>
      {children}
    </PlanRef>
  );
}

const COMPONENTS = {
  a: Link,
  img: ImageText,
  h1: Heading3,
  h2: Heading4,
  h3: Heading5,
  h4: Heading5,
  h5: Heading5,
  h6: Heading5,
  table: Table,
  "pp-seal": SealMarker,
  "pp-plan": PlanMarker,
};

// An answer's Markdown. Raw HTML stays text (no rehype-raw), links are https
// only, and the citation markers become seals and plan links (utils/markers).
// `pending`: still streaming, so markers that can't be resolved yet are hidden.
export default function AnswerBody({
  message,
  content,
  stamp = false,
  pending = false,
  selectedSourceId = null,
  onOpenSource,
  onHoverSource,
}) {
  const options = { sources: message.sources ?? [], plans: message.plans ?? [], pending };
  return (
    <AnswerContext value={{ message, stamp, selectedSourceId, onOpenSource, onHoverSource }}>
      <Markdown remarkPlugins={[remarkGfm, [remarkMarkers, options]]} urlTransform={httpsOnly} components={COMPONENTS}>
        {content}
      </Markdown>
    </AnswerContext>
  );
}
