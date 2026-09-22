# Deploying PolicyPal to Azure

What to create once, what runs on every merge, and what to do when a deploy
goes wrong. The decision behind it is [ADR 0023](../decisions/0023-deploying-to-azure.md).

**The issuer PDFs never leave this machine** (ADR 0016). Nothing below uploads
`data/sbc/`, and ingestion stays local.

## What gets deployed

| Piece | Where | Built by |
| --- | --- | --- |
| API | Container Apps, one replica | `Dockerfile` (ADR 0022) |
| Browser app | Static Web Apps | `npm run build` in CI |
| Database | PostgreSQL Flexible Server + `pgvector` | seeded once, by hand |
| Migrations | Container Apps job, same image | `alembic upgrade head` |

## One-time setup

Names below are placeholders; use your own and set them as repository
variables.

### 1. Resource group, registry, database

```sh
az group create --name policypal-rg --location eastus

az acr create --resource-group policypal-rg --name policypalacr --sku Basic

az postgres flexible-server create \
  --resource-group policypal-rg --name policypal-db \
  --tier Burstable --sku-name Standard_B1ms --version 16 \
  --storage-size 32 --public-access None
az postgres flexible-server parameter set \
  --resource-group policypal-rg --server-name policypal-db \
  --name azure.extensions --value VECTOR
```

`--public-access None` keeps the server off the internet. Migrations run
inside the environment (ADR 0023), so nothing needs to reach it from outside.

### 2. Container Apps environment, the app, and the migration job

```sh
az containerapp env create --resource-group policypal-rg \
  --name policypal-env --location eastus

az containerapp create --resource-group policypal-rg --name policypal-api \
  --environment policypal-env --target-port 8000 --ingress external \
  --min-replicas 0 --max-replicas 1 \
  --registry-server policypalacr.azurecr.io --system-assigned \
  --image policypalacr.azurecr.io/policypal-api:bootstrap

az containerapp job create --resource-group policypal-rg \
  --name policypal-migrate --environment policypal-env \
  --trigger-type Manual --replica-timeout 600 \
  --registry-server policypalacr.azurecr.io --system-assigned \
  --image policypalacr.azurecr.io/policypal-api:bootstrap \
  --command "/app/.venv/bin/alembic" --args "upgrade" "head"
```

**`--max-replicas 1` is load-bearing.** Flask-Limiter keeps its counters in
process, so a second replica doubles every rate limit — including the 5/min on
register and 10/min on login (ADR 0022). Raise it only together with a shared
store for the limiter.

### 3. Settings and secrets on the app

```sh
az containerapp secret set --resource-group policypal-rg --name policypal-api \
  --secrets database-url="postgresql+psycopg://..." \
            openai-key="sk-..." jwt-secret="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"

az containerapp update --resource-group policypal-rg --name policypal-api \
  --set-env-vars ENVIRONMENT=production LOG_DIR=/tmp/logs \
      FRONTEND_ORIGIN="https://<your-static-web-app>.azurestaticapps.net" \
      DATABASE_URL=secretref:database-url \
      OPENAI_API_KEY=secretref:openai-key \
      JWT_SECRET_KEY=secretref:jwt-secret
```

The migration job needs `DATABASE_URL` and the two settings with no default
(`OPENAI_API_KEY`, `JWT_SECRET_KEY`) as well — `Settings` will not construct
without them, even though a migration uses neither.

`.env.example` lists every setting. Never put one in the repo.

### 4. Sign-in without a stored credential

Create an app registration, give it `AcrPush` on the registry and
`Contributor` on the resource group, then add **federated credentials** for
this repository — one for `environment:production`, one for `ref:refs/heads/main`.
No client secret is created (ADR 0023).

### 5. GitHub Environment and variables

Create an Environment named `production` with **yourself as a required
reviewer** — that is the manual approval gate.

| Secret | |
| --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | from the app registration |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | from the Static Web App |

| Variable | Example |
| --- | --- |
| `ACR_NAME` | `policypalacr` |
| `AZURE_RESOURCE_GROUP` | `policypal-rg` |
| `CONTAINERAPP_NAME` | `policypal-api` |
| `MIGRATION_JOB_NAME` | `policypal-migrate` |
| `API_URL` | `https://policypal-api.<region>.azurecontainerapps.io` |
| `FRONTEND_URL` | `https://<name>.azurestaticapps.net` |

### 6. Seed the database, once

The schema comes from migrations; the contents come from here, because
ingestion runs here (ADR 0019).

```sh
pg_dump --no-owner --no-privileges --format=custom \
  -h localhost -U policypal policypal > policypal.dump        # ~75 MB

pg_restore --no-owner --no-privileges --clean --if-exists \
  -d "postgresql://...@policypal-db.postgres.database.azure.com/policypal" policypal.dump
```

This carries the corpus, its chunks, the SBC text, the plan catalog and the
BM25 index row. It does **not** carry the PDFs, and must not.

Afterwards, check the index arrived:

```sql
select name, chunks, built_at from search_indexes;   -- bm25 | 1568 | ...
```

If it is missing, run `make build-index` against the Azure database rather
than re-ingesting: the index is derived from the chunks (ADR 0021).

## Every merge to main

1. CI runs. A failed run never reaches CD.
2. **build** — the image is pushed to ACR, tagged with the commit.
3. **deploy** — waits for your approval, then runs migrations as a job on that
   exact digest, updates the Container App, and polls
   `/api/counties?zip=33101` until it returns 200.
4. **frontend** — builds with `VITE_API_BASE_URL` and uploads to Static Web Apps.

Deploying a specific commit by hand: **Actions → CD → Run workflow**, with a
full 40-character commit id.

## When it goes wrong

**A bad revision is serving.** Roll back to the previous one:

```sh
az containerapp revision list --resource-group policypal-rg --name policypal-api \
  --query "[].{name:name,active:properties.active,created:properties.createdTime}" -o table
az containerapp revision activate --resource-group policypal-rg \
  --name policypal-api --revision <previous-revision>
```

**Migrations failed.** The deploy stops before the app is updated, so the old
revision keeps serving — against a database that may be half migrated. Read
the job's logs, fix forward if you can:

```sh
az containerapp job execution list --resource-group policypal-rg \
  --name policypal-migrate -o table
```

Alembic downgrades exist but are a last resort: reverting a migration that has
already dropped something does not bring it back.

**The API deployed but answers 500.** Almost always the database: either the
restore has not happened, or `search_indexes` is empty. Retrieval says which —
`MissingSearchIndexError` names `make build-index`.

**Cold start feels broken.** The first request after idle loads two models from
the image. It is slow, not stuck. If that stops being acceptable, set
`--min-replicas 1` and pay for it.

## What this does not do

- **No staging environment.** One environment, one reviewer.
- **No alerting.** Failures are seen in the Actions run, not pushed anywhere.
- **No shared rate-limit store**, which is what pins the app at one replica.
- **No scheduled ingestion.** The deployed data is as current as the last
  restore; `checked_at` in `sbc_documents` says how old that is, and
  [sbc.md](sbc.md) is how it is refreshed — locally.
