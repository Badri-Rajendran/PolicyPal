"""Registered corpus sources, run in order by the ingestion pipeline.

Adding a corpus means writing one `Source` subclass, appending it to
ALL_SOURCES, and giving it an entry in registry.toml (ADR 0025). A source the
registry does not enable is left out of SOURCES, so it is never fetched,
chunked or embedded.
"""
from .base import Source
from .healthcare_gov import HealthCareGovSource
from .registry import is_enabled
from .wikipedia import WikipediaSource

ALL_SOURCES: list[Source] = [
    WikipediaSource(),
    HealthCareGovSource(),
]


def enabled_sources(sources: list[Source]) -> list[Source]:
    return [source for source in sources if is_enabled(source.registry_id)]


SOURCES: list[Source] = enabled_sources(ALL_SOURCES)

__all__ = ["ALL_SOURCES", "SOURCES", "HealthCareGovSource", "Source", "WikipediaSource", "enabled_sources"]
