import Button from "../../../components/Button";
import { formatTime } from "../../../utils/formatSource";
import { splitNotices } from "../../../utils/notices";
import PlanComparison from "../../plans/PlanComparison";
import AnswerBody from "./AnswerBody";
import AnswerFooter from "./AnswerFooter";
import Notice from "./Notice";
import StreamingAnswer from "./StreamingAnswer";

// With a plan table, the answer's first paragraph introduces it and the rest
// follows it, as Main.dc.html sets them.
function around(body, hasPlans) {
  if (!hasPlans) return { before: "", after: body };
  const cut = body.indexOf("\n\n");
  return cut === -1 ? { before: body, after: "" } : { before: body.slice(0, cut), after: body.slice(cut + 2) };
}

function Answer({ message, stamp, selectedSourceId, onOpenSource, onHoverSource, onAskAboutPlan }) {
  const { notices, body } = splitNotices(message.content);
  const plans = message.plans ?? [];
  const { before, after } = around(body, plans.length > 0);
  const open = (sourceId) => onOpenSource?.(message, sourceId);
  const bodyProps = { message, stamp, selectedSourceId, onOpenSource: open, onHoverSource };

  return (
    <>
      <div className="a">
        {notices.map((text) => (
          <Notice key={text}>{text}</Notice>
        ))}
        {before && <AnswerBody {...bodyProps} content={before} />}
        {plans.length > 0 && (
          <PlanComparison plans={plans} shownAt={message.created_at} messageId={message.id} onAskAboutPlan={onAskAboutPlan} />
        )}
        {after && <AnswerBody {...bodyProps} content={after} />}
      </div>
      <AnswerFooter message={message} onOpenSource={open} />
    </>
  );
}

// A question, set as the heading, and its answer: saved, streaming, or stopped.
export default function Exchange({
  exchange,
  live = null,
  stopped = false,
  stamp = false,
  selectedSourceId = null,
  onOpenSource,
  onHoverSource,
  onAskAgain,
  onAskAboutPlan,
}) {
  const { question, answer } = exchange;

  return (
    <section className="exchange" aria-label="Question and answer">
      {question && (
        <div className="q">
          <h2>{question.content}</h2>
          <time dateTime={question.created_at}>{formatTime(question.created_at)}</time>
        </div>
      )}
      {answer && (
        <Answer
          message={answer}
          stamp={stamp}
          selectedSourceId={selectedSourceId}
          onOpenSource={onOpenSource}
          onHoverSource={onHoverSource}
          onAskAboutPlan={onAskAboutPlan}
        />
      )}
      {!answer && live && <StreamingAnswer live={live} />}
      {!answer && !live && stopped && question && (
        <div className="stopped">
          <p>You stopped this answer.</p>
          <Button variant="ghost" className="sm" type="button" onClick={() => onAskAgain?.(question.content)}>
            Ask again
          </Button>
        </div>
      )}
    </section>
  );
}
