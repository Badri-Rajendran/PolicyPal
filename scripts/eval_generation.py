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
             Needs the NH, DE, TX and FL SBCs: `make ingest-plans STATES=NH,DE,TX,FL`,
             then `make ingest-sbc STATES=NH,DE`, `make ingest-sbc STATES=TX,FL TOP_ISSUERS=1`
             and `make ingest-sbc STATES=TX ISSUERS=40788,66252`.

  BOUNDARY — does "will my claim be paid?" get the fixed boundary sentence
             and the plan's terms, never a yes or no?

  MISSING DOCUMENTS — a plan whose SBC can't be read here must be named as
             such, with its PDF, and never described from general material
             (ADR 0017). Also needs the NC catalog: `make ingest-plans STATES=NC`.
             Every coverage answer is held to the same rule.

Slow by nature — it loads the LLM and generates once per question — so like
the retrieval eval this is a manual tool, not a CI gate. Run it after any
change to the corpus, retrieval, the prompt, or the model:

    uv run python -m scripts.eval_generation
"""
import re
import sys
from dataclasses import dataclass

from sqlalchemy import select

from src.core.db import get_session
from src.models.plan import Plan
from src.models.sbc import SbcDocument
from src.services.generation import (
    BOUNDARY_SENTENCE,
    NO_ANSWER_RESPONSE,
    ShownPlan,
    answer_query,
    cited_labels,
    reset_token_usage,
    token_usage,
)
from src.services.profile import PlanProfile
from src.services.sbc_status import plan_sbc_status, sbc_document_join

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
MIN_PLAN_SEARCHES = 6
# ADR 0014's sets, measured over three runs: boundary 2/2 every time.
# Coverage was one short of full marks through Phases 2 and 3, for CHRISTUS's
# imaging price: its row wrapped the service name around the price, and the
# answer stated it in 3 of 6 tries. Parser 3 reads that row as one line
# (ADR 0018), the answer states it 6 of 6, and coverage ran 10/10 three times.
# The plan-search profile case varies: 6/8 searches on main at this
# point, so re-run a single miss there before calling it a regression.
MIN_COVERAGE = 10
MIN_BOUNDARY = 2
# ADR 0017: full marks, like the refusals. An answer that describes a plan
# with no document is the failure Phase 4 exists to prevent.
MIN_MISSING = 5


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
# Downtown Los Angeles, rating area 16: plans from the California PUF (ADR 0024).
_CA_PROFILE = PlanProfile(zip_code="90012", age=40, county_fips="06037")
PLAN_SEARCH_SET = [
    ("What silver plans can I buy in 75801? I'm 34.", None),
    ("Compare the bronze plans with the lowest deductibles in ZIP 75801 for a 45-year-old.", None),
    ("Show me some health plans I could buy.", None),
    ("What silver plans can I buy?", _PROFILE),
    # California (ADR 0024): filed rates, and Covered California named, never HealthCare.gov.
    ("What silver plans can I buy?", _CA_PROFILE),
    ("What bronze plans can I get?", _CA_PROFILE),
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
# Phase 3's issuers (ADR 0015), checked by hand against the same PDFs.
_FLORIDA_BLUE = ShownPlan(1, "16842FL0320004", "BlueSelect Silver 1443E ($10 Labs / Adult Dental & Vision / Rewards)",
                          "Florida Blue (BlueCross BlueShield FL)", "Silver", 2026)
_MOLINA = ShownPlan(2, "54172FL0010013", "Molina Bronze Enhanced 3500", "Molina Healthcare", "Bronze", 2026)
_BCBS_TX = ShownPlan(1, "33602TX0460553", "Blue Advantage Silver HMO℠ 205", "Blue Cross and Blue Shield of Texas",
                     "Silver", 2026)
# Oscar's SBC host disallows every path in robots.txt: blocked in ingestion.
_OSCAR = ShownPlan(2, "20069TX0100006", "Silver Classic", "Oscar Insurance Company", "Silver", 2026)
_OSCAR_SBC = "https://d3ul0st9g52g6o.cloudfront.net/2026/TX/sbc/2026_20069TX010000601.pdf"
# BCBS of North Carolina answers every link with a bot challenge: not_pdf.
_BCBS_NC = ShownPlan(1, "11512NC0060002", "Blue Advantage Silver Preferred | 3 Free PCP | $10 Tier 1 Rx | "
                     "Integrated | Nationwide Doctors", "Blue Cross and Blue Shield of NC", "Silver", 2026)
_BCBS_NC_SBC = "https://www.bcbsnc.com/assets/shopper/public/pdf/sbc/Blue_Advantage_Silver_Preferred_2800_2026.pdf"
# Its PDF gives up part of its chart but none of the seven Important
# Questions, so nothing it holds says whether a referral is needed: partial.
_U_UTAH = ShownPlan(1, "42261UT0060024", "U Health Plus Bronze", "University of Utah Health Plans", "Bronze", 2026)
_U_UTAH_SBC = "https://doc.uhealthplan.utah.edu/individual/2026/sbc/uhealthplus/2871148.pdf"
_SBC = " - Summary of Benefits - "


@dataclass(frozen=True)
class Missing:
    """A shown plan whose SBC can't be read here (ADR 0017)."""

    plan: ShownPlan
    # Its status in the database, checked before the case is scored: a case
    # whose plan has since been read must fail as a fixture, never pass.
    status: str
    # Part of its name the answer must use to say which plan it can't read.
    named: str


@dataclass
class CoverageCase:
    query: str
    shown: tuple[ShownPlan, ...]
    must_state: tuple[str, ...]
    # The plans whose SBC must be cited, and no other's.
    cites: tuple[ShownPlan, ...] = ()
    missing: tuple[Missing, ...] = ()
    # Only a definitional question may cite general material.
    corpus_ok: bool = False


COVERAGE_SET = [
    CoverageCase("Does the first one cover MRIs, and what do they cost?", (_WELLSENSE, _HIGHMARK),
                 ("40%",), (_WELLSENSE,)),
    CoverageCase("What does the second plan charge for an emergency room visit?", (_WELLSENSE, _HIGHMARK),
                 ("50%",), (_HIGHMARK,)),
    CoverageCase("Does the first plan cover imaging like an MRI?", (_CHRISTUS, _UHC),
                 ("no charge",), (_CHRISTUS,)),
    # Blocked host: nothing to cite, and the answer must hand over the PDF.
    CoverageCase("Does the second plan cover MRIs?", (_CHRISTUS, _UHC), (_UHC_SBC,),
                 missing=(Missing(_UHC, "blocked", "Silver Standard"),)),
    # A definitional question is the corpus's, never one plan's numbers.
    CoverageCase("What is coinsurance?", (_WELLSENSE, _HIGHMARK), ("coinsurance",), corpus_ok=True),
    # Shown for a year the catalog doesn't hold: no other year's SBC may stand in.
    CoverageCase("Does the first one cover MRIs?",
                 (ShownPlan(1, "13219NH0010002", _WELLSENSE.name, _WELLSENSE.issuer, "Silver", 2025),), ()),
    CoverageCase("What does the first plan charge for lab work?", (_FLORIDA_BLUE, _MOLINA), ("$10",),
                 (_FLORIDA_BLUE,)),
    CoverageCase("What does the second one charge for a primary care visit?", (_FLORIDA_BLUE, _MOLINA),
                 ("$50",), (_MOLINA,)),
    CoverageCase("What does the first plan charge for an emergency room visit?", (_BCBS_TX, _OSCAR),
                 ("$1,000",), (_BCBS_TX,)),
    CoverageCase("Does the second plan cover MRIs?", (_BCBS_TX, _OSCAR), (_OSCAR_SBC,),
                 missing=(Missing(_OSCAR, "blocked", "Silver Classic"),)),
]

# ADR 0017: plans with no readable document, where general material is right
# there in the context to fill the gap.
MISSING_SET = [
    CoverageCase("Does this plan cover MRIs, and what would I pay?", (_BCBS_NC,), (_BCBS_NC_SBC,),
                 missing=(Missing(_BCBS_NC, "not_pdf", "Silver Preferred"),)),
    # Every Marketplace plan covers preventive care: the corpus says so, but
    # not what this plan charges or excludes.
    CoverageCase("Does the second plan cover preventive care, and is it free?", (_CHRISTUS, _UHC), (_UHC_SBC,),
                 missing=(Missing(_UHC, "blocked", "Silver Standard"),)),
    # Mixed: two read, one not. The one not read must be named, not skipped.
    CoverageCase("Compare what these three plans charge for an MRI.", (_FLORIDA_BLUE, _MOLINA, _OSCAR),
                 (_OSCAR_SBC,), (_FLORIDA_BLUE, _MOLINA),
                 missing=(Missing(_OSCAR, "blocked", "Silver Classic"),)),
    CoverageCase("What does the second one charge for an ER visit, and what's its deductible?", (_BCBS_TX, _OSCAR),
                 (_OSCAR_SBC,), missing=(Missing(_OSCAR, "blocked", "Silver Classic"),)),
    # Read in part: none of the seven Important Questions is in what was read,
    # so "referral" appears nowhere in this document's text. The answer must
    # say so rather than conclude the plan needs none (ADR 0017).
    CoverageCase("Does this plan need a referral before I see a specialist?", (_U_UTAH,),
                 (_U_UTAH_SBC, "among what was read"), cites=(_U_UTAH,),
                 missing=(Missing(_U_UTAH, "partial", "U Health Plus"),)),
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
        if profile is _CA_PROFILE:
            named = "Covered California" in result.text and "HealthCare.gov" not in result.text
            print(f"               Covered California named, not HealthCare.gov: {named}")

    print(f"\n  {reached}/{len(PLAN_SEARCH_SET)} plan questions reached search_plans")
    return reached


def _sbc_plans(result) -> set[str]:
    """The plan names whose SBC an answer drew on."""
    return {c.source.split(_SBC)[0] for c in result.chunks if _SBC in c.source}


_URL = re.compile(r"https?://\S+")
_FIGURE = re.compile(r"\$\s?\d|\d\s?%")


def corpus_citations(text: str, shown: tuple[str, ...] = ()) -> list[str]:
    """The general-material labels an answer cites.

    An SBC label names its plan, a link is the issuer's own PDF, and a label
    that is a shown plan's name is the answer saying which plan it could not
    read — none of the three is general material.
    """
    return sorted(label for label in cited_labels(text)
                  if _SBC not in label and not _URL.match(label)
                  and not any(label.startswith(name) for name in shown))


def score_coverage(case: CoverageCase, text: str, cited: set[str],
                   statuses: dict[str, str | None]) -> tuple[str, str] | None:
    """What is wrong with a coverage answer, as a tag and a detail; None when nothing is.

    Judged on the answer's own text, never on what was retrieved: general
    material always reaches the model, and only citing it is the failure.
    """
    for gap in case.missing:
        if statuses.get(gap.plan.plan_id) != gap.status:
            return "FIXTURE", f"{gap.plan.plan_id} is {statuses.get(gap.plan.plan_id)}, not {gap.status}: pick another plan"
    if text == NO_ANSWER_RESPONSE:
        return ("NO ANSWER", "declined") if case.must_state or case.missing else None
    expected = {plan.name for plan in case.cites}
    if cited != expected:
        return "WRONG CITE", f"cited {sorted(cited)}, expected {sorted(expected)}"
    if not case.corpus_ok and (labels := corpus_citations(text, tuple(plan.name for plan in case.shown))):
        return "CORPUS", f"cited general material for a plan: {labels}"
    if unnamed := [gap.named for gap in case.missing if gap.named.lower() not in text.lower()]:
        return "SILENT", f"did not name {unnamed} as unreadable"
    if case.missing and not case.cites and (figure := _FIGURE.search(_without_names(text, case))):
        return "FABRICATED", f"stated {figure.group(0)!r} with no document to state it from"
    if missing := [term for term in case.must_state if term.lower() not in text.lower()]:
        return "INCOMPLETE", f"did not state {missing}"
    return None


def _without_names(text: str, case: CoverageCase) -> str:
    """The answer without links or plan names, whose own figures ("$10 Tier 1 Rx") are no claim."""
    for plan in case.shown:
        text = text.replace(plan.name, "")
    return _URL.sub("", text)


def _statuses(cases: list[CoverageCase]) -> dict[str, str | None]:
    """Each missing plan's SBC status now, for the year it was shown."""
    gaps = [gap.plan for case in cases for gap in case.missing]
    with get_session() as session:
        return {
            plan.plan_id: session.scalar(
                select(plan_sbc_status())
                .select_from(Plan)
                .outerjoin(SbcDocument, sbc_document_join())
                .where(Plan.hios_plan_id == plan.plan_id, Plan.plan_year == plan.plan_year)
            )
            for plan in gaps
        }


def _run_coverage_cases(title: str, cases: list[CoverageCase]) -> int:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)

    statuses = _statuses(cases)
    correct = 0
    tokens = []
    for case in cases:
        reset_token_usage()
        result = answer_query(case.query, shown_plans=case.shown)
        tokens.append(token_usage())
        problem = score_coverage(case, result.text, _sbc_plans(result), statuses)
        corpus = sum(_SBC not in c.source for c in result.chunks)

        if problem:
            tag, detail = problem
            print(f"  {'[' + tag + ']':<12} {case.query}")
            print(f"               {detail}")
        else:
            correct += 1
            print(f"  [ok]         {case.query}")
        print(f"               {corpus} corpus sources listed, {len(result.chunks) - corpus} SBC passages, "
              f"{tokens[-1]} tokens")
        print(f"               -> {result.text.strip()[:220]}")

    print(f"\n  {correct}/{len(cases)} answers held")
    print(f"  tokens per answer: {min(tokens)}-{max(tokens)}, mean {sum(tokens) // len(tokens)}")
    return correct


def run_coverage() -> int:
    return _run_coverage_cases("COVERAGE — is a shown plan's term stated from its own SBC?", COVERAGE_SET)


def run_missing() -> int:
    return _run_coverage_cases("MISSING DOCUMENTS — a plan with no readable SBC is named, never described",
                               MISSING_SET)


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
    honest = run_missing()

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

    if honest < MIN_MISSING:
        failures.append(
            f"missing documents {honest} < floor {MIN_MISSING} — a plan with no readable SBC was "
            "described, cited from general material, or left unnamed"
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
