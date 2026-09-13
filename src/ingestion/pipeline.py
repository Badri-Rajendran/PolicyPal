from src.core.logging import get_logger, setup_logging

from . import chunk, embed
from .sources import SOURCES


def _fetch_all() -> None:
    for source in SOURCES:
        source.fetch()


def _normalize_all() -> None:
    for source in SOURCES:
        source.normalize()


STAGES = [
    ("Phase 1: Fetch", _fetch_all),
    ("Phase 2: Normalize", _normalize_all),
    ("Phase 3: Chunk", chunk.execute),
    ("Phase 4: Embed", embed.execute),
]


def main():
    setup_logging()

    logger = get_logger(__name__)
    logger.info("Ingestion pipeline starting")

    for name, stage in STAGES:
        print(f"\n=== Running {name} ===")
        stage()
        print(f"\n=== {name} Completed ===")


if __name__ == "__main__":
    main()
