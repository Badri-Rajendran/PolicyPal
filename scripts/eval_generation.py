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

  PLAN SEARCH — does a question about specific plans reach search_plans
             (ADR 0010)? The reverse is checked in ANSWERS: a definitional
             question that searches plans does not count as answered.
             Needs Anderson County, TX in the catalog:
             `uv run python -m src.ingestion.plans --states TX --max-counties 1`.

  COVERAGE — does a question about a shown plan's coverage state its SBC
             term and cite that plan's SBC, and only that plan's (ADR 0014)?
             Needs the NH, DE and TX SBCs:
             `make ingest-plans STATES=NH,DE` then `make ingest-sbc STATES=NH,DE,TX`.

  BOUNDARY — does "will my claim be paid?" get the fixed boundary sentence
             and the plan's terms, never a yes or no?

Slow by nature — it loads the LLM and generates once per question — so like
the retrieval eval this is a manual tool, not a CI gate. Run it after any
change to the corpus, retrieval, the prompt, or the model:

    uv run python -m scripts.eval_generation
"""
import re
import sys
from dataclasses import dataclass

from src.services.generation import (
    BOUNDARY_SENTENCE,
    NO_ANSWER_RESPONSE,
    ShownPlan,
    answer_query,
    reset_token_usage,
    token_usage,
)
from src.services.profile import PlanProfile

# Floors, set at the measured baseline — every set scored full marks on
# gpt-5-mini (rewrites on gpt-5-nano), up from 7/8 and 2/3 under the local
# Qwen 0.5B, so the floors are the scores.
#
# There is no temperature to steady this: gpt-5-mini accepts only the default,
# so run-to-run variance is a property of the model rather than something the
# config bounds. Three consecutive runs were identical, which is what makes
# full-marks floors safe to commit; re-check a single-question miss against a
# second run before treating it as a regression.
#
# One run is ~17k tokens, a cent or two.
MIN_CORRECT = 8
MIN_REFUSED = 4
MIN_FOLLOW_UPS = 3
MIN_PLAN_SEARCHES = 4
# ADR 0014's sets, measured over three runs: boundary 2/2 every time; coverage
# 6/6 twice and 5/6 once (one answer left out the term), hence one short.
# The plan-search profile case also varies: 6/8 searches on main at this
# point, so re-run a single miss there before calling it a regression.
MIN_COVERAGE = 5
MIN_BOUNDARY = 2


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
    # Was "How much will my policy cost me?" — with the plan tool that is
    # rightly answered by asking for a ZIP code and age (ADR 0010). Car
    # insurance has no such source.
    "How much will my car insurance cost me?",
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


# 75801 is in Anderson County, TX (48001), and in no other county. The third
# case has neither a profile nor a ZIP or age in the question, so reaching the
# tool means being told to add them. The last has only a saved profile: the
# prompt holds no ZIP or age at all, and the server fills them in (ADR 0012).
_PROFILE = PlanProfile(zip_code="75801", age=34, county_fips="48001")
PLAN_SEARCH_SET = [
    ("What silver plans can I buy in 75801? I'm 34.", None),
    ("Compare the bronze plans with the lowest deductibles in ZIP 75801 for a 45-year-old.", None),
    ("Show me some health plans I could buy.", None),
    ("What silver plans can I buy?", _PROFILE),
]


# Plans as a plan table would have shown them (ADR 0014). The terms are what
# each plan's 2026 SBC states, read by hand against the PDF.
_WELLSENSE = ShownPlan(1, "13219NH0010002", "WellSense Clarity NH Silver 6000 + $0 Rx List + 24/7 Nurse Advice",
                       "WellSense Health Plan", "Silver", 2026)
_HIGHMARK = ShownPlan(2, "76168DE0690001", "my Blue Access Select PPO Bronze 3800",
                      "Highmark Blue Cross Blue Shield Delaware", "Bronze", 2026)
_CHRISTUS = ShownPlan(1, "66252TX0380010", "CHRISTUS Value Silver 70 ($0 Virtual Urgent Care)",
                      "CHRISTUS Health Plan", "Silver", 2026)
# Its issuer's host refuses automated requests: blocked in ingestion.
_UHC = ShownPlan(2, "40220TX0080020", "UHC Silver Standard", "UnitedHealthcare", "Silver", 2026)
_UHC_SBC = "https://www.uhc.com/ifp/sbc.40220TX0080020-01.en.2026.pdf"
_SBC = " - Summary of Benefits - "


@dataclass
class CoverageCase:
    query: str
    shown: tuple[ShownPlan, ...]
    must_state: tuple[str, ...]
    # The plan whose SBC must be cited, alone; None when no SBC may be cited.
    cites: ShownPlan | None


COVERAGE_SET = [
    CoverageCase("Does the first one cover MRIs, and what do they cost?", (_WELLSENSE, _HIGHMARK),
                 ("40%",), _WELLSENSE),
    CoverageCase("What does the second plan charge for an emergency room visit?", (_WELLSENSE, _HIGHMARK),
                 ("50%",), _HIGHMARK),
    CoverageCase("Does the first plan cover imaging like an MRI?", (_CHRISTUS, _UHC),
                 ("no charge",), _CHRISTUS),
    # Blocked host: nothing to cite, and the answer must hand over the PDF.
    CoverageCase("Does the second plan cover MRIs?", (_CHRISTUS, _UHC), (_UHC_SBC,), None),
    # A definitional question is the corpus's, never one plan's numbers.
    CoverageCase("What is coinsurance?", (_WELLSENSE, _HIGHMARK), ("coinsurance",), None),
    # Shown for a year the catalog doesn't hold: no other year's SBC may stand in.
    CoverageCase("Does the first one cover MRIs?",
                 (ShownPlan(1, "13219NH0010002", _WELLSENSE.name, _WELLSENSE.issuer, "Silver", 2025),), (), None),
]

# "Will it be paid?" turns on medical necessity, prior authorization and the
# network, none of which an SBC holds.
BOUNDARY_SET = [
    ("Will my MRI be covered?", (_WELLSENSE, _HIGHMARK), "Does the first one cover MRIs?"),
    ("If I go to the ER tonight, will the second plan pay for it?", (_WELLSENSE, _HIGHMARK), None),
]
_VERDICT = re.compile(r"^\W*(yes|no)\b|\b(yes|no), (it|they|your|the)\b|\bwill (definitely |not )?be (covered|paid)\b",
                      re.IGNORECASE | re.MULTILINE)


def run_answers() -> int:
    print("=" * 78)
    print("ANSWERS — does the generated text state what a correct answer must?")
    print("=" * 78)

    correct = 0

    for case in ANSWER_SET:
        result = answer_query(case.query)
        text = result.text

        if text == NO_ANSWER_RESPONSE:
            print(f"  [NO ANSWER]  {case.query}")
            continue
        if result.plans or result.needs_plan_inputs:
            print(f"  [SEARCHED]   {case.query}")
            print("               searched plans for a definitional question")
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
        result = answer_query(query)
        text, chunks = result.text, result.chunks

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
        first = answer_query(opener).text
        history = [
            {"role": "user", "content": opener},
            {"role": "assistant", "content": first},
        ]
        text = answer_query(case.query, history).text

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


def run_plan_searches() -> int:
    print("\n" + "=" * 78)
    print("PLAN SEARCH — does a question about specific plans reach the tool?")
    print("=" * 78)

    reached = 0

    for query, profile in PLAN_SEARCH_SET:
        result = answer_query(query, profile=profile)

        if result.plans or result.needs_plan_inputs:
            reached += 1
            print(f"  [ok]         {query}")
            print(f"               {len(result.plans)} plans, needs {list(result.needs_plan_inputs)}")
        else:
            print(f"  [NO SEARCH]  {query}")
        print(f"               -> {result.text.strip()[:220]}")

    print(f"\n  {reached}/{len(PLAN_SEARCH_SET)} plan questions reached search_plans")
    return reached


def _sbc_plans(result) -> set[str]:
    """The plan names whose SBC an answer cites."""
    return {c.source.split(_SBC)[0] for c in result.chunks if _SBC in c.source}


def run_coverage() -> int:
    print("\n" + "=" * 78)
    print("COVERAGE — is a shown plan's term stated from its own SBC?")
    print("=" * 78)

    correct = 0
    tokens = []
    for case in COVERAGE_SET:
        reset_token_usage()
        result = answer_query(case.query, shown_plans=case.shown)
        tokens.append(token_usage())
        cited = _sbc_plans(result)
        expected = {case.cites.name} if case.cites else set()
        missing = [term for term in case.must_state if term.lower() not in result.text.lower()]
        corpus = sum(_SBC not in c.source for c in result.chunks)

        if result.text == NO_ANSWER_RESPONSE and case.must_state:
            print(f"  [NO ANSWER]  {case.query}")
        elif cited != expected:
            print(f"  [WRONG CITE] {case.query}")
            print(f"               cited {sorted(cited)}, expected {sorted(expected)}")
        elif missing:
            print(f"  [INCOMPLETE] {case.query}")
            print(f"               did not state {missing}")
        else:
            correct += 1
            print(f"  [ok]         {case.query}")
        print(f"               {corpus} corpus chunks, {len(result.chunks) - corpus} SBC passages, "
              f"{tokens[-1]} tokens")
        print(f"               -> {result.text.strip()[:220]}")

    print(f"\n  {correct}/{len(COVERAGE_SET)} coverage answers stated the term from the right SBC")
    print(f"  tokens per answer: {min(tokens)}-{max(tokens)}, mean {sum(tokens) // len(tokens)}")
    return correct


def run_boundary() -> int:
    print("\n" + "=" * 78)
    print("BOUNDARY — \"will it be paid?\" gets the boundary and terms, never a verdict")
    print("=" * 78)

    held = 0
    for query, shown, opener in BOUNDARY_SET:
        history = []
        if opener:
            first = answer_query(opener, shown_plans=shown).text
            history = [{"role": "user", "content": opener}, {"role": "assistant", "content": first}]
        result = answer_query(query, history, shown_plans=shown)
        # The boundary sentence itself says "will be paid".
        verdict = _VERDICT.search(result.text.replace(BOUNDARY_SENTENCE, ""))

        if BOUNDARY_SENTENCE not in result.text:
            print(f"  [NO BOUNDARY] {query}")
        elif verdict:
            print(f"  [VERDICT]     {query}: {verdict.group(0)!r}")
        elif not _sbc_plans(result):
            print(f"  [NO TERMS]    {query}")
        else:
            held += 1
            print(f"  [ok]          {query}")
        print(f"                -> {result.text.strip()[:220]}")

    print(f"\n  {held}/{len(BOUNDARY_SET)} gave the boundary and cited terms without a verdict")
    return held


def main() -> int:
    correct = run_answers()
    refused = run_refusals()
    followed = run_follow_ups()
    searched = run_plan_searches()
    covered = run_coverage()
    bounded = run_boundary()

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

    if searched < MIN_PLAN_SEARCHES:
        failures.append(
            f"plan searches {searched} < floor {MIN_PLAN_SEARCHES} — a plan question "
            "stopped reaching search_plans"
        )

    if covered < MIN_COVERAGE:
        failures.append(
            f"coverage {covered} < floor {MIN_COVERAGE} — a plan's SBC term was missed, "
            "or another plan's SBC was cited"
        )
    if bounded < MIN_BOUNDARY:
        failures.append(
            f"boundary {bounded} < floor {MIN_BOUNDARY} — a situational question got a verdict "
            "or lost the boundary sentence"
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
