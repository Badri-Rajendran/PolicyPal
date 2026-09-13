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
    response, chunks = answer_query(parsed.query, parsed.top_k)

    print(response)

    if chunks:
        print("\nSources:")
        for chunk in chunks:
            print(f"  - {chunk.source} (chunk {chunk.chunk_id}, relevance {chunk.score:.2f})")


if __name__ == "__main__":
    main()
