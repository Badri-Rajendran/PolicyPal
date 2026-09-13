"""Retrieval quality eval: two complementary measurements over the real corpus.

`tests/` proves the retrieval code is wired correctly with mocked models. It
cannot catch a change that keeps everything wired correctly but quietly makes
real answers worse. This script runs the real `search()` against the real
ingested corpus, and reports two different things:

  ROUTING  — for a question about a known topic, does the document that covers
             that topic come back? Catches embedding/reranking regressions.

  COVERAGE — for a question a real user would ask, does the corpus contain an
             answer *at all*, and does the retrieved text actually carry the
             evidence needed to answer it? Catches the failure routing cannot
             see: retrieval working perfectly over a corpus that simply
             doesn't hold the answer.

Coverage exists because routing alone is self-fulfilling — every routing
question is derived from a document already in the corpus, so it can only
ever pass. The Wikipedia-only corpus scored 25/25 on routing while failing to
answer 12 of these 20 consumer questions. See ADR 0003.

Not a CI gate — it needs the corpus already ingested (`make ingest`) and loads
real embedding/reranker models, so it's slow and environment-dependent by
nature. Run by hand after any change to retrieval, chunking, the models
involved, or the corpus:

    uv run python -m scripts.eval_retrieval
"""
import re
import sys
from dataclasses import dataclass, field

from src.services.retrieval import search

# Routing is scored by rank, so it asks for a fixed window. Coverage passes
# top_k=None so it measures exactly what the API serves (settings.rerank_top_k)
# rather than a number chosen by the eval — an eval that measures different
# retrieval than production is measuring the wrong thing.
ROUTING_TOP_K = 5

# Regression floors, set at the measured baseline. Retrieval is deterministic
# (no sampling anywhere in the path), so a drop below these means a change
# made real answers worse rather than a flaky run. Raise them as the corpus
# grows and the known gaps below get filled.
MIN_ANSWERED = 20
MIN_WITH_EVIDENCE = 20
MIN_ROUTING_TOP5 = 25
MIN_ABSTENTIONS = 4


# Routing: does the topic's own document come back?

@dataclass
class RoutingCase:
    query: str
    # Any of these sources answering counts as correct. A question can have
    # more than one legitimately good source — "what is a deductible" is
    # answered as well by the authoritative glossary entry as by the
    # encyclopedia article, and an eval that insists on one of them scores a
    # genuine improvement as a regression.
    acceptable: tuple[str, ...]


def _wiki(topic: str) -> str:
    return f"wiki_{re.sub(r'[^\w]+', '_', topic).strip('_')}.txt"


ROUTING_SET = [
    RoutingCase("What is a deductible in health insurance?",
                (_wiki("Health_insurance"), "hcg_glossary_Deductible.md",
                 "hcg_glossary_High_Deductible_Health_Plan_HDHP.md")),
    RoutingCase("Who receives the payout when a life insurance policyholder dies?",
                (_wiki("Life insurance"),)),
    RoutingCase("What income does disability insurance replace if someone can't work?",
                (_wiki("Disability insurance"),)),
    RoutingCase("What kind of care does long-term care insurance help pay for?",
                (_wiki("Long-term care insurance"),)),
    RoutingCase("What does a homeowner's policy typically cover?",
                (_wiki("Home insurance"),)),
    RoutingCase("What does renters insurance protect that a landlord's policy doesn't?",
                (_wiki("Renters' insurance"),)),
    RoutingCase("What is property insurance designed to protect against?",
                (_wiki("Property insurance"),)),
    RoutingCase("What is comprehensive coverage in car insurance?",
                (_wiki("Vehicle insurance"),)),
    RoutingCase("What does personal liability insurance cover if someone is injured on your property?",
                (_wiki("Liability insurance"),)),
    RoutingCase("What does travel insurance typically cover if a trip is cancelled?",
                (_wiki("Travel insurance"),)),
    RoutingCase("What veterinary costs does pet insurance typically cover?",
                (_wiki("Pet insurance"),)),
    RoutingCase("Why do homeowners need separate flood insurance?",
                (_wiki("Flood insurance"),)),
    RoutingCase("What does earthquake insurance cover that a standard home policy excludes?",
                (_wiki("Earthquake insurance"),)),
    RoutingCase("What does title insurance protect a homebuyer against?",
                (_wiki("Title insurance"),)),
    RoutingCase("When is a borrower required to pay lenders mortgage insurance?",
                (_wiki("Lenders mortgage insurance"),)),
    RoutingCase("What lost income does business interruption insurance cover?",
                (_wiki("Business interruption insurance"),)),
    RoutingCase("What does workers' compensation pay for an employee injured on the job?",
                (_wiki("Workers' compensation"),)),
    RoutingCase("What is professional liability insurance also known as?",
                (_wiki("Professional liability insurance"),)),
    RoutingCase("Who does D&O insurance protect within a company?",
                (_wiki("Directors and officers liability insurance"),)),
    RoutingCase("Why would a business buy key person insurance?",
                (_wiki("Key person insurance"),)),
    RoutingCase("What risk does trade credit insurance protect a seller against?",
                (_wiki("Trade credit insurance"),)),
    RoutingCase("What costs does cyber insurance help cover after a data breach?",
                (_wiki("Cyber insurance"),)),
    RoutingCase("What does marine insurance cover during ocean transport?",
                (_wiki("Marine insurance"),)),
    RoutingCase("What does aviation insurance cover for aircraft owners?",
                (_wiki("Aviation insurance"),)),
    RoutingCase("What protects farmers against crop yield losses?",
                (_wiki("Crop insurance"),)),
]


# Coverage: does the corpus actually answer what users ask?

@dataclass
class CoverageCase:
    query: str
    kind: str
    # Terms that must appear somewhere in the retrieved context for it to
    # plausibly contain the answer. Deliberately a low bar: this catches
    # "retrieval returned confident nonsense", not answer quality.
    evidence: tuple[str, ...] = field(default=())


COVERAGE_SET = [
    # Definitional-practical: the vocabulary on a user's own paperwork
    # A comparison question needs BOTH concepts in the retrieved context. The
    # earlier evidence terms here were ("coinsurance", "percentage") — both
    # satisfied by coinsurance chunks alone — so this passed while the context
    # never mentioned copay and the generated answer invented the comparison.
    # Every comparison case must name both sides for the same reason.
    CoverageCase("What's the difference between a copay and coinsurance?", "definition",
                 ("copay", "coinsurance")),
    CoverageCase("What is an out-of-pocket maximum?", "definition",
                 ("out-of-pocket", "plan year")),
    CoverageCase("What does 'in-network' mean and why does it matter?", "definition",
                 ("network",)),
    CoverageCase("What is a premium tax credit?", "definition",
                 ("tax credit", "premium")),
    CoverageCase("What is a formulary?", "definition",
                 ("prescription", "drug")),
    # Procedural: how does the user actually do the thing
    CoverageCase("How do I appeal a denied health insurance claim?", "procedural",
                 ("appeal",)),
    CoverageCase("How do I file a claim after a car accident?", "procedural",
                 ("claim",)),
    CoverageCase("What documents do I need to enroll in a health plan?", "procedural",
                 ("enroll",)),
    CoverageCase("How do I cancel my health insurance plan?", "procedural",
                 ("cancel",)),
    CoverageCase("How do I add a newborn to my health insurance?", "procedural",
                 ("plan",)),
    # Eligibility: US-specific regulatory reality
    CoverageCase("Can I get insurance if I have a pre-existing condition?", "eligibility",
                 ("pre-existing",)),
    CoverageCase("What is a special enrollment period and when do I qualify?", "eligibility",
                 ("special enrollment",)),
    CoverageCase("Can I stay on my parents' health insurance at 25?", "eligibility",
                 ("parent", "26")),
    CoverageCase("What happens to my health coverage if I lose my job?", "eligibility",
                 ("cover",)),
    CoverageCase("Do I qualify for Medicaid?", "eligibility",
                 ("medicaid",)),
    # Decision support
    CoverageCase("Should I pick a plan with a lower premium or a lower deductible?", "decision",
                 ("deductible", "premium")),
    CoverageCase("Is a high deductible health plan with an HSA worth it?", "decision",
                 ("deductible",)),
    CoverageCase("How much life insurance coverage do I actually need?", "decision",
                 ("life insurance",)),
    CoverageCase("What is the difference between term life and whole life insurance?",
                 "decision", ("term life", "whole life")),
    CoverageCase("What is the difference between an HMO and a PPO?", "definition",
                 ("hmo", "ppo")),
    CoverageCase("Do I need umbrella insurance?", "decision",
                 ("umbrella",)),
]


# Abstention: questions the corpus should NOT answer

# Asking which product is better *for you*, which company to buy from, or what
# a future premium will be is a request for personalized advice or a
# prediction. A grounded assistant returning nothing is the correct outcome —
# and it is a property worth protecting. Widening retrieval (a lower relevance
# gate, or applying the subquery best-of score to every query instead of only
# to ones that matched nothing) would quietly start answering these from
# whatever chunk happened to be topically nearby.
#
# Only questions verified to abstain today are listed. Some advice-shaped
# questions do still return a confidently-scored but irrelevant source; see
# ADR 0004 — that is a known cross-encoder limitation, not something this set
# pretends is solved.
ABSTENTION_SET = [
    "Term life or whole life — which is better for a young family?",
    "Will my car insurance premium go up next year?",
    "Is State Farm better than Geico?",
    "How much will my policy cost me?",
]


def run_abstention() -> int:
    print("\n" + "=" * 78)
    print("ABSTENTION — advice and prediction questions must return nothing")
    print("=" * 78)

    abstained = 0

    for query in ABSTENTION_SET:
        results = search(query)

        if results:
            print(f"  [ANSWERED]   {query}")
            print(f"                {results[0].score:.2f} {results[0].source}")
        else:
            abstained += 1
            print(f"  [abstained]  {query}")

    print(f"\n  {abstained}/{len(ABSTENTION_SET)} correctly returned nothing")
    return abstained


def run_routing() -> int:
    print("=" * 78)
    print("ROUTING — does the document covering the topic come back?")
    print("=" * 78)

    in_top5 = top1 = 0

    for case in ROUTING_SET:
        results = search(case.query, top_k=ROUTING_TOP_K)
        rank = next(
            (i for i, r in enumerate(results, start=1) if r.source in case.acceptable), None
        )

        in_top5 += rank is not None
        top1 += rank == 1

        if rank is None:
            top = results[0].source if results else "(no results)"
            print(f"  [MISS]    {case.query!r}\n            expected one of {case.acceptable}, "
                  f"top match was {top}")
        elif rank == 1:
            print(f"  [rank 1]  {case.query!r}")
        else:
            print(f"  [rank {rank}]  {case.query!r} (top was {results[0].source})")

    print(f"\n  {in_top5}/{len(ROUTING_SET)} in top {ROUTING_TOP_K}, {top1}/{len(ROUTING_SET)} ranked first")
    return in_top5


def run_coverage() -> tuple[int, int]:
    print("\n" + "=" * 78)
    print("COVERAGE — does the corpus hold an answer to what users actually ask?")
    print("=" * 78)

    answered = with_evidence = 0
    gaps: list[CoverageCase] = []
    thin: list[CoverageCase] = []

    for case in COVERAGE_SET:
        # top_k=None -> production's configured rerank_top_k
        results = search(case.query)

        if not results:
            gaps.append(case)
            print(f"  [NO ANSWER]  ({case.kind}) {case.query}")
            continue

        answered += 1

        context = " ".join(r.content for r in results).lower()
        missing = [term for term in case.evidence if term.lower() not in context]

        if missing:
            thin.append(case)
            print(f"  [NO EVIDENCE] ({case.kind}) {case.query}")
            print(f"                retrieved {results[0].source}, but no mention of {missing}")
        else:
            with_evidence += 1
            print(f"  [OK {results[0].score:.2f}]   ({case.kind}) {case.query}")
            print(f"                {results[0].source}")

    total = len(COVERAGE_SET)
    print(f"\n  {answered}/{total} returned anything above the relevance gate")
    print(f"  {with_evidence}/{total} returned context containing the expected evidence")

    if gaps:
        print("\n  Corpus gaps — nothing relevant exists to retrieve:")
        for case in gaps:
            print(f"    - ({case.kind}) {case.query}")

    if thin:
        print("\n  Retrieved something, but not the evidence to answer:")
        for case in thin:
            print(f"    - ({case.kind}) {case.query}")

    return answered, with_evidence


def main() -> int:
    routing_top5 = run_routing()
    answered, with_evidence = run_coverage()
    abstained = run_abstention()

    print("\n" + "=" * 78)
    failures = []

    if routing_top5 < MIN_ROUTING_TOP5:
        failures.append(
            f"routing top-{ROUTING_TOP_K} {routing_top5} < floor {MIN_ROUTING_TOP5}"
        )
    if answered < MIN_ANSWERED:
        failures.append(f"coverage answered {answered} < floor {MIN_ANSWERED}")
    if with_evidence < MIN_WITH_EVIDENCE:
        failures.append(f"coverage with evidence {with_evidence} < floor {MIN_WITH_EVIDENCE}")
    if abstained < MIN_ABSTENTIONS:
        failures.append(
            f"abstentions {abstained} < floor {MIN_ABSTENTIONS} — retrieval started "
            "answering questions it cannot ground"
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
