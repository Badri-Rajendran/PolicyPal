# 0002 — CI scope: what's automated now vs. deliberately deferred

## Status

Accepted

## Context

CLAUDE.md calls for CI covering lint, tests, coverage, dependency/secret
scanning, SAST, a Docker build + image scan, and an Alembic migration check —
plus CD that pushes images to Azure Container Registry and deploys there.
None of this existed yet. Building all of it at once mixes two very
different kinds of work: checks that need nothing but the repo itself, and
deployment that needs real cloud credentials this environment doesn't have
and shouldn't fabricate.

## Decision

`.github/workflows/ci.yml` runs on every PR to `main` and every push to
`main`, with three jobs — all credential-free:

- **backend**: `ruff check`, `alembic upgrade head` + `alembic check` against
  a `pgvector/pgvector:pg16` service container (catches schema drift before
  it ships), `pytest`, `bandit -ll` (SAST), `pip-audit` (dependency CVEs).
- **frontend**: `npm run lint`, `npm test` (Vitest/RTL), `npm run build`,
  `npm audit --audit-level=high`.
- **secret-scan**: `gitleaks detect` over full git history.

**Deliberately not built yet:**

- **Docker build + image vulnerability scan.** There is no Dockerfile for
  the app. Writing a production one for a Flask service that pulls in
  PyTorch + transformers (a multi-GB dependency tree) is its own real task —
  base image choice, layer caching, non-root user, multi-stage build to
  keep the final image lean — not something to bolt on to get a CI checkbox
  green.
- **CD to Azure (ACR push, migrations, deploy).** Requires an Azure
  subscription, service principal, and GitHub Environment secrets that
  don't exist in this project yet. Configuring cloud deployment
  infrastructure isn't something to set up unprompted or with placeholder
  credentials.
- ~~**Coverage thresholds.**~~ Resolved: `pytest --cov=src --cov-fail-under=80`
  is now the backend test step. 80% is a regression floor set just under
  the measured baseline (81%, concentrated in the API/service layer that
  matters most — infrastructure glue wrapping torch/sentence-transformers
  sits lower by design, since testing it meaningfully would mean asserting
  mocks were called rather than catching real bugs; that surface is
  exercised by `scripts/ask.py` and `scripts/eval_retrieval.py` instead),
  not an arbitrary target. Ratchet it up as real coverage grows.

## Consequences

CI substantively raises the floor (nothing merges with a lint failure, a
test failure, a schema-drift migration, a newly introduced CVE, or a
committed secret) without a false sense of production-readiness the
Docker/Azure sections of CLAUDE.md's CI/CD spec still call for. The next
material step here is a real Dockerfile — recorded as an ADR when it lands,
per the same reasoning that produced this one.
