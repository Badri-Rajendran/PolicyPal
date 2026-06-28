.PHONY: ingest

ingest:
	uv run python -m src.ingestion.pipeline