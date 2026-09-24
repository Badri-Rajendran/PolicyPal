# Deploying PolicyPal to Azure

What to create once, what runs on every merge, and what to do when a deploy
goes wrong. The decision behind it is [ADR 0023](../decisions/0023-deploying-to-azure.md).

**The issuer PDFs never leave this machine** (ADR 0016). Nothing below uploads
`data/sbc/`, and ingestion stays local. The first deployment verified this by
checksumming `data/` before and after: 2,247 files, 1,593 PDFs, identical.

This runbook describes a deployment that was actually performed, not a
proposal. Where the first attempt hit a wall, the wall is documented rather
than smoothed over.

## What is deployed

| Piece | Where | Name |
| --- | --- | --- |
| API | Container Apps, 1 replica, Central US | `policypal-api` |
| Browser app | Static Web Apps (Free), Central US | `policypal-ui` |
| Database | PostgreSQL Flexible Server 16 + `pgvector`, Central US | `policypal-db` |
| Migrations | Container Apps job, same image | `policypal-migrate` |
| Registry | Container Registry, Basic, West US 3 | `policypalcr` |

## Before you start: four subscription limits that shape all of this

These were found by hitting them. On a **Free Trial** subscription
(`quotaId: FreeTrial_2014-09-01`), check each before choosing a region.

1. **Postgres Flexible Server is restricted in many regions.** `eastus`,
   `eastus2`, `westus2` and `southcentralus` all return *"Provisioning is
   restricted in this region."* Only `centralus`, `westus3` and
   `northcentralus` worked. Check with:
   ```sh
   az postgres flexible-server list-skus -l <region> -o json | head -5
   ```
2. **One Container Apps environment per subscription — globally.** Not per
   region. The per-region `ManagedEnvironmentCount` usage API reports
   `limit=1` for each region independently, which is true and misleading; the
   create fails with `MaxNumberOfGlobalEnvironmentsInSubExceeded`. **Try the
   create before planning around a region.**
3. **ACR Tasks are not permitted.** `az acr build` fails with
   `TasksOperationsNotAllowed`, so the image must be built elsewhere.
4. **The spending limit is ON**, so exhausting credit deallocates resources
   rather than billing. Budget accordingly.

## One-time setup

### 1. Resource group, registry, database

```sh
az group create --name policypal-rg --location westus3

az acr create --resource-group policypal-rg --name policypalcr \
  --sku Basic --location westus3

# Central US, because Postgres is restricted elsewhere (see limit 1) and the
# shared Container Apps environment lives there.
az postgres flexible-server create \
  --resource-group policypal-rg --name policypal-db --location centralus \
  --admin-user ppadmin --admin-password "$PGPASS" \
  --tier Burstable --sku-name Standard_B1ms --version 16 \
  --storage-size 32 --public-access <your.ip.address> --yes

az postgres flexible-server parameter set \
  --resource-group policypal-rg --server-name policypal-db \
  --name azure.extensions --value VECTOR

az postgres flexible-server firewall-rule create \
  --resource-group policypal-rg --server-name policypal-db \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0
```

**Generate the password as hex** (`openssl rand -hex 24`). Alembic passes
`DATABASE_URL` through a ConfigParser that interpolates `%`, so a password
containing one breaks migrations in a way that is tedious to diagnose.

**The server is public, behind a firewall — not `--public-access None`.** An
earlier version of this runbook said otherwise and was self-contradictory: the
seed in step 5 restores from your laptop, and a consumption Container Apps
environment has no VNet path to a private server. Public plus two firewall
rules is what actually works. Azure enforces TLS regardless.

**`az postgres flexible-server db create` rejected every flag spelling** in
CLI 2.90.0. Create the database with psql instead:

```sh
psql "host=policypal-db.postgres.database.azure.com user=ppadmin \
  dbname=postgres sslmode=require" -c "CREATE DATABASE policypal;"
```

### 2. Build and push the image

`az acr build` is unavailable (limit 3), and a Mac builds `arm64` while
Container Apps needs `amd64`. Build locally for the right platform:

```sh
az acr login -n policypalcr          # AAD token; admin user stays disabled

docker buildx build --platform linux/amd64 --file Dockerfile \
  --tag policypalcr.azurecr.io/policypal-api:"$(git rev-parse HEAD)" \
  --tag policypalcr.azurecr.io/policypal-api:latest \
  --push .
```

Measured on an M-series Mac under QEMU: **270s total** — `uv sync` 118s, both
models baked 56s, push 158s. Emulation overhead was far smaller than expected,
because the build is dominated by network and disk rather than CPU. The result
is **639 MB compressed** in the registry. Confirm the platform before
deploying — an arm64 image fails at pull time with an unhelpful message:

```sh
az acr manifest list-metadata -r policypalcr -n policypal-api -o json \
  | python3 -c "import sys,json;[print(m.get('architecture'),m.get('os')) for m in json.load(sys.stdin)]"
```

### 3. The app and the migration job

There is no `:bootstrap` image — build the real one first (step 2) and create
the app directly on its digest.

```sh
ENVID=$(az containerapp env show -g <env-rg> -n <env-name> --query id -o tsv)
IMG=policypalcr.azurecr.io/policypal-api@sha256:<digest>

az containerapp create --resource-group policypal-rg --name policypal-api \
  --environment "$ENVID" --image "$IMG" \
  --target-port 8000 --ingress external \
  --cpu 1.0 --memory 2.0Gi --min-replicas 1 --max-replicas 1 \
  --system-assigned \
  --registry-server policypalcr.azurecr.io --registry-identity system \
  --secrets database-url="$DBURL" openai-key="$OPENAI" \
            jwt-secret="$JWT" cms-key="$CMS" \
  --env-vars ENVIRONMENT=production LOG_DIR=/tmp/logs \
      DATABASE_URL=secretref:database-url \
      OPENAI_API_KEY=secretref:openai-key \
      JWT_SECRET_KEY=secretref:jwt-secret \
      CMS_MARKETPLACE_API_KEY=secretref:cms-key
```

**`--registry-identity system` is what grants `AcrPull`.** Without it the
identity exists but cannot pull, and the revision never starts. Verify:

```sh
PID=$(az containerapp show -g policypal-rg -n policypal-api --query identity.principalId -o tsv)
az role assignment list --assignee "$PID" --all -o tsv   # expect AcrPull on policypalcr
```

**`--max-replicas 1` is load-bearing.** Flask-Limiter keeps its counters in
process, so a second replica doubles every rate limit — including 5/min on
register and 10/min on login (ADR 0022). Raise it only together with a shared
store. `--min-replicas 1` avoids a cold start and is the more expensive
choice; `0` is correct if idle cost matters more than first-request latency.

`LOG_DIR=/tmp/logs` is required, not cosmetic: uid 10001 cannot write `/app`,
and `setup_logging()` creates the directory at import, so a bad value crashes
startup before the app serves anything.

The migration job takes the same image and the same three required settings —
`Settings` is constructed at import, so the job crashes without them even
though a migration uses none of them:

```sh
az containerapp job create --resource-group policypal-rg \
  --name policypal-migrate --environment "$ENVID" --image "$IMG" \
  --trigger-type Manual --replica-timeout 600 \
  --cpu 0.5 --memory 1.0Gi --mi-system-assigned \
  --registry-server policypalcr.azurecr.io --registry-identity system \
  --secrets database-url="$DBURL" openai-key="$OPENAI" jwt-secret="$JWT" \
  --env-vars DATABASE_URL=secretref:database-url \
      OPENAI_API_KEY=secretref:openai-key \
      JWT_SECRET_KEY=secretref:jwt-secret \
      LOG_DIR=/tmp/logs ENVIRONMENT=production \
  --command "/app/.venv/bin/alembic" --args "upgrade" "head"
```

### 4. The browser app

```sh
az staticwebapp create --name policypal-ui --resource-group policypal-rg \
  --location centralus --sku Free
```

Static Web Apps exists only in Central US, East US 2, West US 2, West Europe
and East Asia. It is CDN-served, so the region is metadata.

```sh
TOKEN=$(az staticwebapp secrets list --name policypal-ui \
  --resource-group policypal-rg --query properties.apiKey -o tsv)

cd frontend
VITE_API_BASE_URL="https://<api-fqdn>" npm run build
grep -r "127.0.0.1" dist/ && echo "STOP: localhost leaked into the bundle"

npx @azure/static-web-apps-cli deploy ./dist \
  --deployment-token "$TOKEN" --env production
```

**Grep the bundle.** `frontend/.env` pins `VITE_API_BASE_URL` to
`http://127.0.0.1:5000`. A shell variable does take precedence, but verifying
the artifact costs one command and catches the case where it does not.

Then point CORS at it — exact match, **no trailing slash**:

```sh
az containerapp update --resource-group policypal-rg --name policypal-api \
  --set-env-vars FRONTEND_ORIGIN="https://<swa-host>"
```

A mismatch breaks the browser app silently while every curl check still
passes, because curl ignores CORS. Verify with an `Origin` header:

```sh
curl -si -H "Origin: https://<swa-host>" "https://<api-fqdn>/api/counties?zip=33101" \
  | grep -i access-control-allow-origin
```

### 5. Seed the database, once

The schema comes from the dump along with the data, so `alembic upgrade head`
afterwards is a no-op — correct, not skipped.

**Use the container's `pg_dump`.** A v15 client refuses a v16 server, and
macOS Postgres installs are often older than the dev container:

```sh
docker exec policypal_db pg_dump --no-owner --no-privileges \
  --format=custom -U policypal -d policypal > policypal.dump    # ~10 MB

docker exec -i -e PGPASSWORD="$PGPASS" policypal_db pg_restore \
  --no-owner --no-privileges \
  --dbname "host=policypal-db.postgres.database.azure.com user=ppadmin \
            dbname=policypal sslmode=require" < policypal.dump
```

Verify against the source, not against expectations:

```sql
select count(*) from chunks;          -- 1568
select count(*) from sbc_chunks;      -- 35756
select count(*) from plans;           -- 3276
select count(*) from zip_counties;    -- 56280
select name, chunks from search_indexes;   -- bm25 | 1568
select version_num from alembic_version;   -- f6e50c4aec26
```

If `search_indexes` is missing, run `make build-index` against the Azure
database rather than re-ingesting: the index is derived from the chunks
(ADR 0021).

**Azure ships pgvector 0.8.2; the dev container has 0.8.6.** The restore is
clean because the corpus uses only the plain `vector` type and cosine
distance, both stable across those versions. Worth knowing before adopting a
newer pgvector feature locally.

### 6. Sign-in without a stored credential

Create an app registration, give it `AcrPush` on the registry and
`Contributor` on the resource group, then add **federated credentials** for
this repository — one for `environment:production`, one for
`ref:refs/heads/main`. No client secret is created (ADR 0023).

### 7. GitHub Environment and variables

Create an Environment named `production` with **yourself as a required
reviewer** — that is the manual approval gate. Two jobs reference it, so
**approval is requested twice per deploy**.

| Secret | |
| --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | from the app registration |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | `az staticwebapp secrets list` |

| Variable | Value |
| --- | --- |
| `ACR_NAME` | `policypalcr` |
| `AZURE_RESOURCE_GROUP` | `policypal-rg` |
| `CONTAINERAPP_NAME` | `policypal-api` |
| `MIGRATION_JOB_NAME` | `policypal-migrate` |
| `API_URL` | the API origin, **no trailing slash** |
| `FRONTEND_URL` | the Static Web App origin |

## Verifying a deployment

Creation succeeding is not the same as the app working. In order:

```sh
az containerapp revision list -g policypal-rg -n policypal-api \
  --query "[].{rev:name,state:properties.runningState}" -o table   # RunningAtMaxScale

curl -s -w '%{http_code}\n' "$API/api/counties?zip=33101"   # 200, Miami-Dade
curl -s -o /dev/null -w '%{http_code}\n' "$API/api/auth/me" # 401, not 500
```

Then ask a real question through the API or the UI and confirm the answer
carries **citations**. That is the only check that proves all three of: both
models loaded from the image under `HF_HUB_OFFLINE=1`, the BM25 index came
from Postgres, and pgvector search ran. Measured on the first deployment:
`/api/counties` **0.43s**, a full cited RAG answer **13s**.

Finally, run the migration job once by hand. It should succeed as a no-op, and
it proves CD's migration step works before CD ever runs:

```sh
az containerapp job start -g policypal-rg -n policypal-migrate
az containerapp job execution list -g policypal-rg -n policypal-migrate \
  --query "[0].properties.status" -o tsv    # Succeeded
```

## Every merge to main

1. CI runs. A failed run never reaches CD.
2. **build** — the image is pushed to ACR, tagged with the commit.
3. **deploy** — waits for your approval, then runs migrations as a job on that
   exact digest, updates the Container App, and polls
   `/api/counties?zip=33101` until it returns 200.
4. **frontend** — builds with `VITE_API_BASE_URL` and uploads to Static Web Apps.

Note that the health poll is **data-dependent**: `/api/counties?zip=33101`
returns 404 on a migrated-but-unseeded database, so step 5 must have run or
the deploy job fails against a perfectly healthy app.

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

**The revision will not start.** Check `AcrPull` first (step 3), then whether
the image is amd64 (step 2), then whether all three required settings are
present — a missing one fails at import, before any log line is written.

**The browser app shows nothing but the API answers curl.** CORS. Compare
`FRONTEND_ORIGIN` to the Static Web App origin character for character.

**Cold start feels broken.** The first request after idle loads two models from
the image. It is slow, not stuck. At `--min-replicas 1` this does not arise.

## What this does not do

- **No staging environment.** One environment, one reviewer — and on a Free
  Trial, one environment is the hard limit anyway.
- **No dedicated environment.** The app shares a Container Apps environment,
  and therefore a Log Analytics workspace, with another project.
- **No alerting.** Failures are seen in the Actions run, not pushed anywhere.
- **No shared rate-limit store**, which is what pins the app at one replica.
- **No scheduled ingestion.** The deployed data is as current as the last
  restore; `checked_at` in `sbc_documents` says how old that is, and
  [sbc.md](sbc.md) is how it is refreshed — locally.
