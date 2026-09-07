const PROMPTS = [
  "What does my deductible actually cover?",
  "How does coinsurance differ from a copay?",
  "What's typically excluded from a homeowner's policy?",
];

export default function EmptyState({ onPrompt }) {
  return (
    <div className="empty-state">
      <h2>Ask about your policy</h2>
      <p>PolicyPal answers from a curated set of insurance references and always shows where an answer came from.</p>
      <ul className="prompt-list">
        {PROMPTS.map((prompt) => (
          <li key={prompt}>
            <button type="button" onClick={() => onPrompt(prompt)}>
              {prompt}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
