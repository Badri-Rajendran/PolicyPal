import { useEffect, useRef, useState } from "react";
import ErrorBanner from "../../../components/ErrorBanner";
import { toExchanges } from "../../../utils/exchanges";
import { sourceNumbers } from "../../../utils/markers";
import EmptyState from "./EmptyState";
import Exchange from "./Exchange";
import JumpToLatest from "./JumpToLatest";
import "./transcript.css";

// Within this of the bottom, new text keeps the view pinned there.
const PINNED_PX = 80;
// Further than this above it, "Jump to latest" appears (spec §4.3).
const JUMP_PX = 200;

// What a screen reader hears when an answer finishes: the streaming region is
// replaced by the saved answer, which announces nothing. Sources are counted
// as the seals number them, one per document.
function readyText(messages, finishedId) {
  const answer = finishedId && messages.find((m) => m.id === finishedId);
  if (!answer) return "";
  const count = sourceNumbers(answer.sources).size;
  if (count === 0) return "Answer ready";
  return `Answer ready, ${count} ${count === 1 ? "source" : "sources"}`;
}

function Content({ messages, status, error, onPrompt, onRetry, children }) {
  if (status === "loading" && messages.length === 0) {
    return (
      <p className="transcript-state" role="status">
        Loading conversation…
      </p>
    );
  }
  // Before the empty check: a thread that failed to load has no messages either,
  // and the starters would hide that its history is missing.
  if (status === "error") {
    return (
      <div className="transcript-state">
        <ErrorBanner>{error || "This conversation couldn't be loaded."}</ErrorBanner>
        <button type="button" className="link" onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  }
  if (messages.length === 0) return <EmptyState onPrompt={onPrompt} />;
  return children;
}

// The thread as question-and-answer exchanges, kept at the bottom while an
// answer streams unless the reader scrolls up.
export default function Transcript({
  messages,
  status,
  error,
  live = null,
  stoppedId = null,
  finishedId = null,
  selectedSourceId = null,
  onPrompt,
  onRetry,
  onAskAgain,
  onOpenSource,
  onHoverSource,
  onAskAboutPlan,
}) {
  const scrollRef = useRef(null);
  const endRef = useRef(null);
  const pinned = useRef(true);
  const [away, setAway] = useState(false);
  const exchanges = toExchanges(messages);

  function onScroll() {
    const el = scrollRef.current;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    pinned.current = distance <= PINNED_PX;
    setAway(distance > JUMP_PX);
  }

  function jump() {
    pinned.current = true;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ block: "end", behavior: still ? "auto" : "smooth" });
  }

  // The scroll position is the DOM's: follow new text only while pinned. A
  // question just sent (a draft appearing) is always shown, and pins the view
  // again, wherever the reader had scrolled to.
  const drafting = useRef(false);
  useEffect(() => {
    if (live && !drafting.current) pinned.current = true;
    drafting.current = Boolean(live);
    if (pinned.current) endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, live]);

  return (
    <>
      <div className="scroll" ref={scrollRef} onScroll={onScroll}>
        <Content messages={messages} status={status} error={error} onPrompt={onPrompt} onRetry={onRetry}>
          <div className="column">
            {exchanges.map((exchange) => {
              const isLive = live && exchange.question && !exchange.answer && exchange.question.id === live.questionId;
              return (
                <Exchange
                  key={exchange.key}
                  exchange={exchange}
                  live={isLive ? live : null}
                  stopped={Boolean(exchange.question) && exchange.question.id === stoppedId}
                  stamp={Boolean(exchange.answer) && exchange.answer.id === finishedId}
                  selectedSourceId={selectedSourceId}
                  onOpenSource={onOpenSource}
                  onHoverSource={onHoverSource}
                  onAskAgain={onAskAgain}
                  onAskAboutPlan={onAskAboutPlan}
                />
              );
            })}
          </div>
        </Content>
        <div className="transcript-end" ref={endRef} />
      </div>
      {away && <JumpToLatest onClick={jump} />}
      {/* Always mounted, and empty while an answer streams, so the next
          answer is announced even when its text is the same as the last. */}
      <p className="visually-hidden" role="status">
        {live ? "" : readyText(messages, finishedId)}
      </p>
    </>
  );
}
