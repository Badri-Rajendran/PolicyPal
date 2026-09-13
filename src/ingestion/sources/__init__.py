"""Registered corpus sources, run in order by the ingestion pipeline.

Adding a corpus means writing one `Source` subclass and appending it here;
no pipeline, chunking, or embedding code changes.
"""
from .base import Source
from .healthcare_gov import HealthCareGovSource
from .wikipedia import WikipediaSource

SOURCES: list[Source] = [
    WikipediaSource(),
    HealthCareGovSource(),
]

__all__ = ["SOURCES", "HealthCareGovSource", "Source", "WikipediaSource"]
