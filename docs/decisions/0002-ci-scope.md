# 0002 — CI scope: what's automated now vs. deliberately deferred

## Status

Accepted. All three deferrals below have since been closed: coverage
thresholds in Phase 3, the Docker build and image scan by ADR 0022, and CD to
Azure by ADR 0023.

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

**Deferred when this was written; all three have since been built:**

- ~~**Docker build + image vulnerability scan.**~~ **Resolved by ADR 0022.**
  It was its own real task, as expected: CPU-only torch, both models baked in
  at their pinned revisions, a non-root multi-stage build, and a CI step that
  runs the image to prove no issuer PDF reached it. 2.48 GB, scanned by Trivy
  on every pull request.
- ~~**CD to Azure (ACR push, migrations, deploy).**~~ **Resolved by ADR 0023**,
  once a subscription existed. Container Apps, Static Web Apps and a Flexible
  Server, deployed by digest behind a required reviewer, with migrations run
  as a job inside the environment so the database needs no public opening.
  Sign-in is OIDC, so no Azure credential is stored here after all.
- ~~**Coverage thresholds.**~~ Resolved: `pytest --cov=src --cov-fail-under=85`
  is now the backend test step. It is a regression floor set just under the
  measured baseline, not an arbitrary target — infrastructure glue wrapping
  torch/sentence-transformers sits lower by design, since testing it
  meaningfully would mean asserting mocks were called rather than catching
  real bugs; that surface is exercised by `scripts/ask.py` and
  `scripts/eval_retrieval.py` instead. Ratcheted from 80% to 85% when the
  ingestion restructure (ADR 0003) brought the baseline to 88%.

## Consequences

CI substantively raises the floor (nothing merges with a lint failure, a
test failure, a schema-drift migration, a newly introduced CVE, or a
committed secret) without a false sense of production-readiness the
Docker/Azure sections of CLAUDE.md's CI/CD spec still call for. The next
material step here is a real Dockerfile — recorded as an ADR when it lands,
per the same reasoning that produced this one.
