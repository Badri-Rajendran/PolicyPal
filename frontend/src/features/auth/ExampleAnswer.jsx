import { useState } from "react";
import Seal from "../chat/transcript/Seal";
import "../chat/transcript/transcript.css";
import "../chat/sources/sources.css";

// HealthCare.gov glossary text (public domain), as SignIn.dc.html shows it.
const QUOTES = [
  { number: 1, title: "Copayment", quote: "A fixed amount you pay for a plan-covered service, like $30." },
  { number: 2, title: "Coinsurance", quote: "A percentage of the cost that you pay for each plan-covered service, like 20%." },
];

// What an answer looks like: a claim, its seal, and the passage behind it.
export default function ExampleAnswer() {
  const [selected, setSelected] = useState(null);
  const seal = (number) => <Seal number={number} stamp index={number - 1} selected={selected === number} onClick={() => setSelected(number)} />;

  return (
    <div className="example" role="group" aria-label="An example answer">
      <div className="q">
        <h2>How is coinsurance different from a copay?</h2>
      </div>
      <div className="a">
        <p>
          A copayment is a fixed amount you pay for a covered service, like $30.{seal(1)} Coinsurance is the percentage of
          the cost you pay for each covered service, like 20%.{seal(2)}
        </p>
      </div>
      <div className="example-sources">
        {QUOTES.map(({ number, title, quote }) => (
          <article key={number} className={selected === number ? "src sel" : "src"}>
            <div className="src-top">
              <span className="seal" aria-hidden="true">
                {number}
              </span>
              <div>
                <div className="src-title">{title}</div>
                <div className="src-kind">HealthCare.gov glossary</div>
              </div>
            </div>
            <p className="quote">{quote}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
