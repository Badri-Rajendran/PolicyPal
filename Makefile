.PHONY: ingest migrate api

ingest:
	uv run python -m src.ingestion.pipeline

migrate:
	uv run alembic upgrade head

api:
	uv run flask --app src.api.main run --debug