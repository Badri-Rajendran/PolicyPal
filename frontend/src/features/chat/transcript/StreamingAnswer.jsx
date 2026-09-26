import { Check } from "lucide-react";
import AnswerBody from "./AnswerBody";
import Notice from "./Notice";

const STAGES = {
  understanding: "Understanding your question",
  searching: "Searching the references",
  plans: "Searching plans near you",
  coverage: "Reading Summaries of Benefits",
  writing: "Writing the answer",
};

// Nothing is cited or priced until `done`; the draft has no sources or plans.
const DRAFT = { id: "draft", sources: [], plans: [] };

// The stages received, in order, then "Writing the answer" until it arrives.
// Every step before the last received one is done; that one is in progress.
function stepsFor(stages) {
  const known = stages.filter((stage) => Object.hasOwn(STAGES, stage));
  const steps = known.map((stage, i) => ({ stage, state: i === known.length - 1 ? "current" : "done" }));
  if (!known.includes("writing")) steps.push({ stage: "writing", state: "pending" });
  return steps;
}

const MARKS = {
  done: (
    <span className="ok" aria-hidden="true">
      <Check className="i" />
    </span>
  ),
  current: <span className="now" aria-hidden="true" />,
  pending: <span className="todo" aria-hidden="true" />,
};

const STATUS = { done: " (done)", current: " (in progress)", pending: "" };

// An answer as it streams in (Streaming.dc.html): progress steps, notices,
// then the text so far with a caret.
export default function StreamingAnswer({ live }) {
  return (
    <div className="a" aria-live="polite" aria-busy="true">
      <ol className="steps" aria-label="Progress">
        {stepsFor(live.stages).map(({ stage, state }) => (
          <li key={stage} data-state={state} className={state === "pending" ? "pending" : undefined}>
            {MARKS[state]}
            {STAGES[stage]}
            {STATUS[state] && <span className="visually-hidden">{STATUS[state]}</span>}
          </li>
        ))}
      </ol>
      {live.notices.map((text) => (
        <Notice key={text}>{text}</Notice>
      ))}
      {live.text && (
        <div className="caret-end">
          <AnswerBody message={DRAFT} content={live.text} pending />
        </div>
      )}
    </div>
  );
}
