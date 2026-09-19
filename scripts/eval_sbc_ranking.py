"""SBC ranking eval: does the right section reach the model? (ADR 0014)

A coverage answer reads the four sections `plan_coverage` ranks highest for
one plan. This asks ten fixed questions of two plans per issuer with stored
SBCs, and counts how often the section that answers each question is among
those four, and first. Read-only; no model is called.

Run it before and after a parser change, or once new issuers are stored:

    uv run python -m scripts.eval_sbc_ranking
    uv run python -m scripts.eval_sbc_ranking --year 2026 --plans-per-issuer 3
"""
import argparse
import sys
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select

from src.core.db import get_session
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcDocument
from src.services.plan_coverage import coverage_for
from src.services.sbc_status import sbc_document_join

# Phase 2 measured 78/80 and Phase 3 200/200 in the top four.
MIN_TOP4 = 0.97

# Each question, and the sections that answer it.
QUESTIONS = [
    ("Is an MRI covered, and what does it cost?", {"If you have a test"}),
    ("Is acupuncture covered?", {"Services your plan does not cover", "Other covered services"}),
    ("Do I need a referral to see a specialist?", {"Do you need a referral to see a specialist?"}),
    ("What does the emergency room cost?", {"If you need immediate medical attention"}),
    ("How much is a generic prescription?", {"If you need drugs to treat your illness or condition"}),
    ("What is the deductible?", {"What is the overall deductible?"}),
    ("What is the most I would pay in a year?", {"What is the out-of-pocket limit for this plan?"}),
    ("Does it cover therapy for depression?",
     {"If you need mental health, behavioral health, or substance abuse services"}),
    ("What does it cost to have a baby?", {"If you are pregnant", "Coverage example: Peg is having a baby"}),
    ("Does it cover my child's eye exam?", {"If your child needs dental or eye care"}),
]
_SBC = " - Summary of Benefits - "


def sample(session, year: int, per_issuer: int) -> dict[str, list[str]]:
    """Plans with a stored SBC, `per_issuer` of each issuer's spread over its list, by issuer name."""
    rows = session.execute(
        select(Issuer.name, Plan.hios_plan_id)
        .join(Issuer, Issuer.id == Plan.issuer_id)
        .join(SbcDocument, sbc_document_join())
        .where(Plan.plan_year == year, SbcDocument.status == "ok")
        .order_by(Issuer.name, Plan.hios_plan_id)
    ).all()
    plans = defaultdict(list)
    for issuer, plan_id in rows:
        plans[issuer].append(plan_id)
    return {issuer: ids[:: max(1, len(ids) // per_issuer)][:per_issuer] for issuer, ids in plans.items()}


def section(label: str) -> str:
    return label.split(_SBC, 1)[1].removesuffix(".pdf")


def main(args=sys.argv[1:]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--plans-per-issuer", type=int, default=2)
    parsed = parser.parse_args(args)

    top4 = first = total = 0
    with get_session() as session:
        for issuer, plan_ids in sample(session, parsed.year, parsed.plans_per_issuer).items():
            hits = []
            for plan_id in plan_ids:
                for question, answers in QUESTIONS:
                    [coverage] = coverage_for(session, [plan_id], question, {plan_id: parsed.year})
                    ranked = [section(p.source) for p in coverage.passages]
                    hits.append((bool(answers & set(ranked)), bool(ranked and ranked[0] in answers)))
                    if not hits[-1][0]:
                        print(f"  MISS {plan_id}: {question!r} got {ranked}")
            top4 += sum(h for h, _ in hits)
            first += sum(f for _, f in hits)
            total += len(hits)
            print(f"{issuer}: top 4 {sum(h for h, _ in hits)}/{len(hits)}, first {sum(f for _, f in hits)}/{len(hits)}")

    if not total:
        print(f"No stored SBCs for {parsed.year}.")
        return 1
    print(f"\nright section in the top 4: {top4}/{total}; ranked first: {first}/{total}")
    if top4 < MIN_TOP4 * total:
        print(f"REGRESSION: top 4 below {MIN_TOP4:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    from src.core.logging import setup_logging

    setup_logging()
    sys.exit(main())
