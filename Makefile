.PHONY: ingest build-index ingest-plans ingest-sbc refresh-sbc sbc-report migrate api \
        ui-dev ui-build ui-lint ui-preview ui-test test lint check

# The plan year to work on; the commands default to the calendar year, which
# is the wrong one once the next year's plans are on sale. e.g. YEAR=2027
YEAR_ARG = $(if $(YEAR),--year $(YEAR))

ingest:
	uv run python -m src.ingestion.pipeline

# Rebuild the BM25 index from the chunks already stored, with no fetching,
# chunking or embedding (ADR 0021). `make ingest` does this as its last step;
# this is for a database seeded from a dump.
build-index:
	uv run python -m src.ingestion.build_index

# STATES is required: comma-separated codes, or ALL for every HealthCare.gov
# state. No default, so a bare `make ingest-plans` cannot start thousands of
# requests. e.g. make ingest-plans STATES=TX,FL
ingest-plans:
	@test -n "$(STATES)" || { echo "STATES is required, e.g. make ingest-plans STATES=TX,FL (or STATES=ALL)"; exit 2; }
	uv run python -m src.ingestion.plans --states $(STATES) $(YEAR_ARG)

# Summary of Benefits PDFs for the catalog plans in STATES; run ingest-plans
# first. Required for the same reason. e.g. make ingest-sbc STATES=NH,DE
# TOP_ISSUERS=1 reads only the largest parent companies' plans, ISSUERS=40788,66252
# only those HIOS issuers' (ADR 0015). Downloaded PDFs are always kept (ADR 0016).
ingest-sbc:
	@test -n "$(STATES)" || { echo "STATES is required, e.g. make ingest-sbc STATES=NH,DE (or STATES=ALL)"; exit 2; }
	uv run python -m src.ingestion.sbc --states $(STATES) $(YEAR_ARG) $(if $(TOP_ISSUERS),--top-issuers) $(if $(ISSUERS),--issuers $(ISSUERS))

# Ask every stored document whether the issuer has changed it, and retry the
# failures ingest-sbc skips. Monthly; see docs/runbooks/sbc.md.
refresh-sbc:
	@test -n "$(STATES)" || { echo "STATES is required, e.g. make refresh-sbc STATES=NH,DE (or STATES=ALL)"; exit 2; }
	uv run python -m src.ingestion.sbc --refresh --states $(STATES) $(YEAR_ARG) $(if $(TOP_ISSUERS),--top-issuers) $(if $(ISSUERS),--issuers $(ISSUERS))

# How much of the catalog has a Summary of Benefits behind it, and what is
# missing, per state and issuer. Reads only. VERIFY=1 also hashes every kept
# PDF. e.g. make sbc-report YEAR=2026 STATES=FL,TX VERIFY=1
sbc-report:
	uv run python -m src.ingestion.sbc.report $(YEAR_ARG) $(if $(STATES),--states $(STATES)) $(if $(VERIFY),--verify-files)

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

# What CI runs, in one command, so "it passed locally" means the same thing.
test:
	uv run pytest -q --cov=src --cov-report=term-missing --cov-fail-under=85

lint:
	uv run ruff check .

check: lint test
	uv run alembic check
	uv run bandit -r src -ll
	uv run pip-audit
