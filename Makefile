.PHONY: ingest ingest-plans ingest-sbc migrate api \
        ui-dev ui-build ui-lint ui-preview ui-test

ingest:
	uv run python -m src.ingestion.pipeline

# STATES is required: comma-separated codes, or ALL for every HealthCare.gov
# state. No default, so a bare `make ingest-plans` cannot start thousands of
# requests. e.g. make ingest-plans STATES=TX,FL
ingest-plans:
	@test -n "$(STATES)" || { echo "STATES is required, e.g. make ingest-plans STATES=TX,FL (or STATES=ALL)"; exit 2; }
	uv run python -m src.ingestion.plans --states $(STATES)

# Summary of Benefits PDFs for the catalog plans in STATES; run ingest-plans
# first. Required for the same reason. e.g. make ingest-sbc STATES=NH,DE
# TOP_ISSUERS=1 reads only the largest parent companies' plans, ISSUERS=40788,66252
# only those HIOS issuers'; KEEP_PDFS=1 keeps the downloaded PDFs, for tuning the
# parser (ADR 0015).
ingest-sbc:
	@test -n "$(STATES)" || { echo "STATES is required, e.g. make ingest-sbc STATES=NH,DE (or STATES=ALL)"; exit 2; }
	uv run python -m src.ingestion.sbc --states $(STATES) $(if $(TOP_ISSUERS),--top-issuers) $(if $(ISSUERS),--issuers $(ISSUERS)) $(if $(KEEP_PDFS),--keep-pdfs)

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
