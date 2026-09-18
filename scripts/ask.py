"""Manual smoke-test CLI for the RAG pipeline: retrieve, generate, print sources."""
import argparse
import sys

from src.services.generation import answer_query


def parse_args(args):
    parser = argparse.ArgumentParser(description="Ask PolicyPal an insurance question.")
    parser.add_argument("-q", "--query", required=True, type=str, help="Question to ask")
    parser.add_argument("-t", "--top_k", required=False, type=int, default=None,
                        help="Number of chunks to retrieve as context")
    return parser.parse_args(args)


def main(args=sys.argv[1:]):
    parsed = parse_args(args)
    result = answer_query(parsed.query, top_k=parsed.top_k)

    print(result.text)

    if result.chunks:
        print("\nSources:")
        for chunk in result.chunks:
            print(f"  - {chunk.source} (chunk {chunk.chunk_id}, relevance {chunk.score:.2f})")

    if result.plans:
        print("\nPlans:")
        for plan in result.plans:
            premium = f"${plan.monthly_premium}/mo" if plan.premium_is_live else "no live premium"
            print(f"  - {plan.hios_plan_id} {plan.name} ({plan.metal_level}, {premium})")

    if result.needs_plan_inputs:
        print(f"\nNeeds: {', '.join(result.needs_plan_inputs)}")


if __name__ == "__main__":
    main()
