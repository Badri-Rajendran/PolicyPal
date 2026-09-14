.PHONY: ingest migrate api \
        ui-dev ui-build ui-lint ui-preview ui-test

ingest:
	uv run python -m src.ingestion.pipeline

migrate:
	uv run alembic upgrade head

api:
	uv run flask --app src.api.main run --debug

ui-dev:
	cd frontend && npm run dev

ui-build:
	cd frontend && npm run build

ui-lint:
	cd frontend && npm run lint

ui-preview:
	cd frontend && npm run preview

ui-test:
	cd frontend && npm test
