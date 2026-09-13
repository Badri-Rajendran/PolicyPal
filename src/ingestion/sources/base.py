"""The contract every corpus source implements.

Each source owns the three things that genuinely differ between corpora —
how documents are fetched, how they are normalized to markdown, and what
chunking strategy suits their shape — and nothing else. Embedding and
storage stay source-agnostic downstream, so adding a corpus means adding
one module and registering it, never editing the pipeline.
"""
from abc import ABC, abstractmethod


class Source(ABC):
    """One corpus source, run as three ordered phases."""

    #: Short identifier used in chunk ids and file prefixes (e.g. "wikipedia").
    name: str

    @abstractmethod
    def fetch(self) -> None:
        """Phase 1 — download raw documents into `constants.RAW`.

        Must be idempotent: skip anything already downloaded so a re-run is
        cheap and doesn't hammer the upstream service.
        """

    @abstractmethod
    def normalize(self) -> None:
        """Phase 2 — convert this source's raw documents to markdown in
        `constants.MARKDOWN`."""

    @abstractmethod
    def chunk_documents(self) -> list[dict]:
        """Phase 3 — split this source's markdown into chunk records.

        Returns records built via `chunking.make_chunk`, so every source
        yields the same shape regardless of its internal strategy.
        """
