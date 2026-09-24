# 0023 — Deploying to Azure: Container Apps, Static Web Apps, Flexible Server

## Status

Accepted. Closes the second of ADR 0002's two deferred items ("CD to Azure
(ACR push, migrations, deploy)"). Depends on ADR 0022 for the image, and on
ADR 0021 without which a deployed container cannot answer.

## Context

ADR 0002 deferred CD because it "requires an Azure subscription, service
principal, and GitHub Environment secrets that don't exist in this project
yet". A subscription now exists.

One constraint shapes everything: **the issuer PDFs stay on the machine that
downloaded them** (ADR 0016), and ADR 0019 already records that "nothing here
can run in CI or in the cloud". Ingestion, refresh and the reports are local
operations. What deploys is the API and the browser app; what travels is the
text already extracted, not the documents it came from.

## Decision

### Container Apps for the API

- **Scale-to-zero** suits a project with no steady traffic, and the revision
  model gives rollback for free.
- **Revisions are the rollback.** Reactivating the previous revision is one
  command, which is what ADR 0002's "keep rollback a single re-run" asks for.
- **One replica, for now.** ADR 0022 explains why: Flask-Limiter has no shared
  storage, so a second replica would double every rate limit. Raising the
  replica count and adding a Redis backend for the limiter are the same piece
  of work, and neither happens by accident.

App Service was the alternative. It costs more at idle for the same thing.
AKS is far more operational surface than one Flask service justifies.

### Static Web Apps for the browser app

A Vite build is static files. Static Web Apps serves them on a CDN with SPA
fallback routing, on a free tier. The API stays a separate origin, which is
what `frontend_origin` and the single-origin CORS rule already assume.

`VITE_API_BASE_URL` is baked in at build time, because Vite has no runtime
configuration. The deployed frontend is therefore tied to one API origin, and
changing it is a rebuild.

### The database is seeded once, by hand, and never by CI

Azure Database for PostgreSQL Flexible Server with `pgvector`.

- **`pg_dump` → `pg_restore`, once.** 75 MB: the corpus, its 1,568 chunks, the
  31,359 SBC chunks, the plan catalog, and the BM25 index row (ADR 0021).
- **Not a migration and not a workflow step.** Seeding is an operator action
  with the local database in front of them, because that is where the data
  lives and where ingestion will keep running.
- **The PDFs are not uploaded.** Nothing in this decision moves
  `data/sbc/` anywhere.

### Migrations run in Azure, on the image being deployed

`alembic upgrade head` runs as a **Container Apps job** using the same image
and digest that is about to serve traffic.

The alternative — running Alembic from the GitHub runner — needs the database
to accept connections from GitHub's IP ranges. That is a public opening on the
database for the sake of a deploy step. Running it inside the environment
keeps the server private, and guarantees the schema is migrated by exactly the
code that will then use it.

### Deployed by digest, gated by a human

- **The image is pushed with the commit as its tag and deployed by digest.**
  A tag can be moved; a digest cannot. What a reviewer approves is exactly
  what runs.
- **`workflow_run` on a successful CI run is the trigger.** A push that fails
  CI never reaches the deploy workflow — "green CI" is a precondition, not a
  convention.
- **`environment: production` with a required reviewer** is the manual
  approval. Nothing reaches Azure until a person says so.
- **A post-deploy check** requests `/api/counties?zip=` until it returns 200,
  so a revision that starts but cannot serve fails the run rather than sitting
  there.

### No Azure credential is stored in GitHub

`azure/login` with **OIDC federated credentials**: the workflow presents a
short-lived GitHub token, and Azure trusts it for this repository and
environment. There is no client secret to rotate or to leak. `id-token:
write` is granted at the workflow level and `contents: read` everywhere else.

`workflow_dispatch` takes a commit to deploy, which a human types, so it is
checked against `^[0-9a-f]{40}$` before it reaches `ref:` or an image tag.

## Consequences

- **Cold starts are slow**, because scale-to-zero means loading two models
  from the image on the first request after idling. The trade is cost; the
  fix, if it stops being acceptable, is a minimum of one replica.
- **A deploy needs a human.** Deliberate. This application answers questions
  about people's health coverage, and there is no staging environment to catch
  a bad revision first.
- **There is no staging environment.** One environment, one reviewer. Adding
  staging is worth doing before the first user who is not the author.
- **The deployed data is a snapshot.** Ingestion runs locally, so the cloud
  database is as current as its last restore. The runbook says how to refresh
  it, and `checked_at` in `sbc_documents` says how old it is.
- **Costs are real but small**: Container Apps scaled to zero, a free Static
  Web App, and a Flexible Server that cannot scale to zero and is therefore
  the monthly floor.
- **Still not done:** a shared rate-limit store, a staging environment, and
  alerting. Named here rather than discovered later.
