"""Retrieval quality eval: a small golden set of insurance questions, each
mapped to the article that should answer it.

Unlike tests/test_retrieval.py (which mocks sparse/dense search and only
proves the orchestration logic — candidate merging, threshold filtering —
is wired correctly), this runs the real search() against the real ingested
corpus. It's the only thing in the repo that would catch a retrieval
*quality* regression: a chunking, embedding, or reranking change that still
passes every mocked unit test but quietly makes real answers worse.

Not a CI gate — it needs the corpus already ingested (`make ingest`) and
loads real embedding/reranker models, so it's slow and environment-
dependent by nature. Run by hand after any change to retrieval, chunking,
or the models involved:

    uv run python -m scripts.eval_retrieval
"""
import re

from src.services.retrieval import search

# One question per ingested article, phrased the way a user actually asks
# rather than restating the article title, so this measures real semantic
# retrieval rather than a keyword-matching layup.
GOLDEN_SET = [
    ("What is a deductible in health insurance?", "Health_insurance"),
    ("Who receives the payout when a life insurance policyholder dies?", "Life_insurance"),
    ("What income does disability insurance replace if someone can't work?", "Disability_insurance"),
    ("What kind of care does long-term care insurance help pay for?", "Long_term_care_insurance"),
    ("What does a homeowner's policy typically cover?", "Home_insurance"),
    ("What does renters insurance protect that a landlord's policy doesn't?", "Renters_insurance"),
    ("What is property insurance designed to protect against?", "Property_insurance"),
    ("What is comprehensive coverage in car insurance?", "Vehicle_insurance"),
    ("What does personal liability insurance cover if someone is injured on your property?", "Liability_insurance"),
    ("What does travel insurance typically cover if a trip is cancelled?", "Travel_insurance"),
    ("What veterinary costs does pet insurance typically cover?", "Pet_insurance"),
    ("Why do homeowners need separate flood insurance?", "Flood_insurance"),
    ("What does earthquake insurance cover that a standard home policy excludes?", "Earthquake_insurance"),
    ("What does title insurance protect a homebuyer against?", "Title_insurance"),
    ("When is a borrower required to pay lenders mortgage insurance?", "Lenders_mortgage_insurance"),
    ("What lost income does business interruption insurance cover?", "Business_interruption_insurance"),
    ("What does workers' compensation pay for an employee injured on the job?", "Workers_compensation"),
    ("What is professional liability insurance also known as?", "Professional_liability_insurance"),
    ("Who does D&O insurance protect within a company?", "Directors_and_officers_liability_insurance"),
    ("Why would a business buy key person insurance?", "Key_person_insurance"),
    ("What risk does trade credit insurance protect a seller against?", "Trade_credit_insurance"),
    ("What costs does cyber insurance help cover after a data breach?", "Cyber_insurance"),
    ("What does marine insurance cover during ocean transport?", "Marine_insurance"),
    ("What does aviation insurance cover for aircraft owners?", "Aviation_insurance"),
    ("What protects farmers against crop yield losses?", "Crop_insurance"),
]


def _source_matches(source: str, expected_topic: str) -> bool:
    sanitized = re.sub(r"[^\w]+", "_", expected_topic).strip("_")
    return source == f"wiki_{sanitized}.txt"


def main() -> None:
    hits = 0
    top1_hits = 0

    for query, expected_topic in GOLDEN_SET:
        results = search(query, top_k=5)
        rank = next((i for i, r in enumerate(results, start=1) if _source_matches(r.source, expected_topic)), None)
        hits += rank is not None
        top1_hits += rank == 1

        if rank is None:
            top = results[0].source if results else "(no results)"
            print(f"[FAIL] {query!r} -> expected article not in top 5 (top match was {top})")
        elif rank == 1:
            print(f"[PASS] {query!r} -> rank 1")
        else:
            print(f"[PASS, rank {rank}] {query!r} -> top match was {results[0].source} instead")

    print(f"\n{hits}/{len(GOLDEN_SET)} in top 5, {top1_hits}/{len(GOLDEN_SET)} ranked first")


if __name__ == "__main__":
    from src.core.logging import setup_logging

    setup_logging()
    main()
