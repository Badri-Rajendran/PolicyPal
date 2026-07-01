.PHONY: ingest migrate

ingest:
	uv run python -m src.ingestion.pipeline

migrate:
	uv run alembic upgrade head