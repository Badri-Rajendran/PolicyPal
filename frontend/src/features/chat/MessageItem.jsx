import { formatSourceLabel, formatTime } from "../../utils/formatSource";
import PlanComparison from "../plans/PlanComparison";

export default function MessageItem({ message }) {
  const isAssistant = message.role === "assistant";
  const hasPlans = isAssistant && message.plans?.length > 0;

  return (
    <article className={`message message-${message.role}${hasPlans ? " message-with-plans" : ""}`}>
      <p className="message-meta">
        <span className="message-author">{isAssistant ? "PolicyPal" : "You"}</span>
        <time dateTime={message.created_at}>{formatTime(message.created_at)}</time>
      </p>
      <p className="message-body">{message.content}</p>

      {hasPlans && <PlanComparison plans={message.plans} shownAt={message.created_at} />}

      {isAssistant && message.sources?.length > 0 && (
        <div className="message-sources">
          <h3>Sources</h3>
          <ol>
            {message.sources.map((source, index) => (
              <li key={`${source.chunk_id}-${index}`}>
                <span className="source-label">{formatSourceLabel(source.source)}</span>
                <span className="source-relevance">{Math.round(source.relevance * 100)}% match</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </article>
  );
}
