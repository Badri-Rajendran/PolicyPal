from . import download
from . import clean
from . import chunk
from . import embed
from src.core.logging import get_logger, setup_logging

STAGES = [
    ("Phase 1", download.wikipedia_data),
    ("Phase 2", clean.wikipedia_data),
    ("Phase 3", chunk.execute),
    ("Phase 4", embed.execute),
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