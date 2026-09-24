# 0023 — Deploying to Azure: Container Apps, Static Web Apps, Flexible Server

## Status

Accepted, and **amended by the first real deployment** — see "What deploying
it actually changed" at the end. Four of the choices below did not survive
contact with the subscription. Closes the second of ADR 0002's two deferred
items ("CD to Azure (ACR push, migrations, deploy)"). Depends on ADR 0022 for
the image, and on ADR 0021 without which a deployed container cannot answer.

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
  model gives rollback for free. (The deployment runs one replica instead —
  see the amendment.)
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

- **`pg_dump` → `pg_restore`, once.** A 78 MB database, 10 MB as a
  custom-format dump: the corpus, its 1,568 chunks, the 35,756 SBC chunks, the
  3,276-plan catalog, and the BM25 index row (ADR 0021). (An earlier draft said
  31,359 SBC chunks — that count predated the ADR 0020 robots.txt refresh.)
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

- **Cold starts are slow** whenever scale-to-zero is used, because the first
  request after idling loads two models from the image. The trade is cost; the
  deployment took the other side of it and runs one replica always.
- **A deploy needs a human.** Deliberate. This application answers questions
  about people's health coverage, and there is no staging environment to catch
  a bad revision first.
- **There is no staging environment.** One environment, one reviewer. Adding
  staging is worth doing before the first user who is not the author.
- **The deployed data is a snapshot.** Ingestion runs locally, so the cloud
  database is as current as its last restore. The runbook says how to refresh
  it, and `checked_at` in `sbc_documents` says how old it is.
- **Costs are real.** Scaled to zero the floor would be the Flexible Server,
  which cannot scale to zero. As deployed, with one replica always running,
  the API dominates instead — see the amendment for measured figures.
- **Still not done:** a shared rate-limit store, a staging environment, and
  alerting. Named here rather than discovered later.

## What deploying it actually changed

The estate above was built on 2026-09-24. Four decisions changed, each forced
by a subscription limit rather than chosen. They are recorded here because the
reasoning above is still right in principle and wrong in fact.

### The region was chosen for us

Postgres Flexible Server is **restricted in `eastus`, `eastus2`, `westus2` and
`southcentralus`** on this subscription — `list-skus` returns "Provisioning is
restricted in this region." Only `centralus`, `westus3` and `northcentralus`
were open. Everything now runs in **Central US**, except the registry in West
US 3, where it was created before the constraint was understood. Cross-region
pull costs one transfer per revision and is not worth moving.

### The Container Apps environment is shared, not dedicated

A Free Trial subscription permits **one Container Apps environment globally**,
and another project already held it. `policypal-api` therefore runs inside
that environment and shares its Log Analytics workspace. This is real coupling
and the first thing to undo on a paid subscription.

Worth recording how this was missed: the per-region usage API reports
`ManagedEnvironmentCount limit=1` for every region independently, which reads
as "one per region" and is not. Only the failed create says
`MaxNumberOfGlobalEnvironmentsInSubExceeded`.

### The database is public behind a firewall, not private

The original text said `--public-access None` and claimed migrations running
inside the environment made that sufficient. It does not: a consumption
environment has no VNet path to a private server, and the one-off seed
restores from a laptop. The server now has a public endpoint with two firewall
rules — the operator's IP and Azure services. TLS is enforced by Azure either
way. Making this genuinely private needs a VNet-integrated workload profile
environment, which the limit above also forbids.

### It does not scale to zero

"Scale-to-zero suits a project with no steady traffic" was the original
reasoning and is still sound; the deployment nonetheless runs
`--min-replicas 1` by explicit choice, trading roughly **$70/month** for the
absence of a cold start. At 1 vCPU / 2 GiB that is the dominant line item —
Postgres B1ms is ~$16, the registry ~$5, Static Web Apps free. Setting
`--min-replicas 0` is a one-word change and the right one if idle cost ever
matters more than first-request latency.

### Two smaller things worth knowing

- **ACR Tasks are not permitted** on this subscription, so `az acr build`
  fails. The image is built with `docker buildx --platform linux/amd64` —
  necessary anyway, since an Apple Silicon Mac otherwise produces an arm64
  image that Container Apps refuses. 270s under emulation, 639 MB compressed.
- **Azure ships pgvector 0.8.2 against 0.8.6 locally.** Harmless today because
  the corpus uses only the plain `vector` type, but it bounds which pgvector
  features are safe to adopt.

### What the deployment proved

Measured, not assumed: `/api/counties?zip=33101` returns 200 in **0.43s**; an
unauthenticated `/api/auth/me` returns **401**; a full RAG answer with
citations takes **13s**, which demonstrates both models loading from the image
under `HF_HUB_OFFLINE=1` and the BM25 index loading from Postgres. The
migration job was run once by hand and succeeded. `data/` was checksummed
before and after and is byte-identical — 2,247 files, 1,593 PDFs (ADR 0016).
