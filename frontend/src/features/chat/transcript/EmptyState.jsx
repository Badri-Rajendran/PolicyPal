const STARTERS = [
  { kind: "Plans near you", text: "Compare silver plans near me" },
  { kind: "Plans near you", text: "Which bronze plans are HSA-eligible?" },
  { kind: "A term", text: "How is coinsurance different from a copay?" },
  { kind: "A rule", text: "Can I buy a plan outside open enrollment?" },
];

// A new question (Empty.dc.html): the heading and four starters that fill the composer.
export default function EmptyState({ onPrompt }) {
  return (
    <div className="hello">
      <h1>What would you like to know about your coverage?</h1>
      <p className="lede">
        Answers come from plans' Summaries of Benefits and Coverage, HealthCare.gov and other references. Every claim
        links to the passage it came from.
      </p>
      <div className="starters">
        {STARTERS.map(({ kind, text }) => (
          <button key={text} type="button" className="starter" onClick={() => onPrompt(text)}>
            <span className="k">{kind}</span>
            <span className="t">{text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
