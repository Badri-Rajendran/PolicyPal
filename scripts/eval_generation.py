"""Generation quality eval: is the ANSWER right, not just the context?

`scripts/eval_retrieval.py` grades context — whether the right chunks come
back. That is necessary but not sufficient, and the gap between them is not
theoretical: coverage read 19/20 while "What's the difference between a copay
and coinsurance?" was answering that "coinsurance is higher than in-network
coinsurance because it allows for more flexibility in payment terms" —
fabricated, and never mentioning copay. No retrieval metric could see it,
because retrieval metrics do not measure answers (ADR 0004).

This runs the full `answer_query()` path and checks two things:

  ANSWERS  — does the generated text state the facts a correct answer must
             state? A deliberately low bar: it catches fabrication and
             non-answers, not prose quality.

  REFUSALS — when nothing clears the relevance gate, does the pipeline return
             the fallback rather than inventing something? This is the
             hallucination guard, and it is the half that protects users.

Slow by nature — it loads the LLM and generates once per question — so like
the retrieval eval this is a manual tool, not a CI gate. Run it after any
change to the corpus, retrieval, the prompt, or the model:

    uv run python -m scripts.eval_generation
"""
import sys
from dataclasses import dataclass

from src.services.generation import NO_ANSWER_RESPONSE, answer_query

# Floors, set at the measured baseline. Generation samples at
# settings.temperature (0.2), so unlike retrieval this is not perfectly
# deterministic — a single-question miss on a re-run is worth re-checking
# before treating it as a regression.
MIN_CORRECT = 7
MIN_REFUSED = 4
MIN_FOLLOW_UPS = 2


@dataclass
class AnswerCase:
    query: str
    # Every term must appear in the generated answer. Kept to facts the
    # source material states plainly, so a miss means the model failed to use
    # its context rather than that it phrased things differently.
    must_state: tuple[str, ...]


ANSWER_SET = [
    # The regression case: both sides of a comparison must actually be stated.
    AnswerCase("What's the difference between a copay and coinsurance?",
               ("copay", "coinsurance", "percentage")),
    AnswerCase("What is a deductible?", ("deductible",)),
    AnswerCase("What is an out-of-pocket maximum?", ("out-of-pocket",)),
    AnswerCase("What is a formulary?", ("drug",)),
    AnswerCase("What is a premium tax credit?", ("premium",)),
    AnswerCase("What is a Special Enrollment Period?", ("enrollment",)),
    AnswerCase("Can I stay on my parents' health insurance at 25?", ("26",)),
    AnswerCase("Why do homeowners need separate flood insurance?", ("flood",)),
]

# Nothing in the corpus grounds these: two ask for advice or a prediction
# (ADR 0004's abstention reasoning), one is simply off-domain. Inventing an
# answer to any of them is the failure this set exists to catch.
REFUSAL_SET = [
    "Is State Farm better than Geico?",
    "How much will my policy cost me?",
    "Will my car insurance premium go up next year?",
    "What is the capital of France?",
]

# Follow-ups: the second question is meaningless on its own, so it only works
# if the rewrite resolves it against the first (ADR 0005). Before that landed,
# every one of these returned NO_ANSWER_RESPONSE.
FOLLOW_UP_SET = [
    ("What is a deductible?", AnswerCase("What about for auto insurance?", ("deductible",))),
    ("What is a copay?", AnswerCase("How is that different from coinsurance?", ("coinsurance",))),
    ("What is an out-of-pocket maximum?", AnswerCase("Does it include my premium?", ("premium",))),
]


def run_answers() -> int:
    print("=" * 78)
    print("ANSWERS — does the generated text state what a correct answer must?")
    print("=" * 78)

    correct = 0

    for case in ANSWER_SET:
        text, _ = answer_query(case.query)

        if text == NO_ANSWER_RESPONSE:
            print(f"  [NO ANSWER]  {case.query}")
            continue

        missing = [term for term in case.must_state if term.lower() not in text.lower()]

        if missing:
            print(f"  [INCOMPLETE] {case.query}")
            print(f"               did not state {missing}")
            print(f"               -> {text.strip()[:220]}")
        else:
            correct += 1
            print(f"  [ok]         {case.query}")
            print(f"               -> {text.strip()[:220]}")

    print(f"\n  {correct}/{len(ANSWER_SET)} answers stated the expected facts")
    return correct


def run_refusals() -> int:
    print("\n" + "=" * 78)
    print("REFUSALS — ungrounded questions must not be answered")
    print("=" * 78)

    refused = 0

    for query in REFUSAL_SET:
        text, chunks = answer_query(query)

        if text == NO_ANSWER_RESPONSE:
            refused += 1
            print(f"  [refused]    {query}")
        else:
            print(f"  [ANSWERED]   {query}")
            print(f"               -> {text.strip()[:220]}")
            print(f"               from {[c.source for c in chunks][:3]}")

    print(f"\n  {refused}/{len(REFUSAL_SET)} correctly refused")
    return refused


def run_follow_ups() -> int:
    print("\n" + "=" * 78)
    print("FOLLOW-UPS — does a question that needs the conversation get answered?")
    print("=" * 78)

    answered = 0

    for opener, case in FOLLOW_UP_SET:
        first, _ = answer_query(opener)
        history = [
            {"role": "user", "content": opener},
            {"role": "assistant", "content": first},
        ]
        text, _ = answer_query(case.query, history)

        if text == NO_ANSWER_RESPONSE:
            print(f"  [NO ANSWER]  {opener} -> {case.query}")
            continue

        missing = [term for term in case.must_state if term.lower() not in text.lower()]

        if missing:
            print(f"  [INCOMPLETE] {opener} -> {case.query}")
            print(f"               did not state {missing}")
        else:
            answered += 1
            print(f"  [ok]         {opener} -> {case.query}")

        print(f"               -> {text.strip()[:220]}")

    print(f"\n  {answered}/{len(FOLLOW_UP_SET)} follow-ups resolved against the conversation")
    return answered


def main() -> int:
    correct = run_answers()
    refused = run_refusals()
    followed = run_follow_ups()

    print("\n" + "=" * 78)
    failures = []

    if correct < MIN_CORRECT:
        failures.append(f"answers {correct} < floor {MIN_CORRECT}")
    if refused < MIN_REFUSED:
        failures.append(
            f"refusals {refused} < floor {MIN_REFUSED} — the pipeline answered "
            "something it cannot ground"
        )
    if followed < MIN_FOLLOW_UPS:
        failures.append(
            f"follow-ups {followed} < floor {MIN_FOLLOW_UPS} — the rewrite stopped "
            "resolving questions against their conversation"
        )

    if failures:
        print("REGRESSION: " + "; ".join(failures))
        return 1

    print("All floors met.")
    return 0


if __name__ == "__main__":
    from src.core.logging import setup_logging

    setup_logging()
    sys.exit(main())
