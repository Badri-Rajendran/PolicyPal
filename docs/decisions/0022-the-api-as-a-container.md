# 0022 — The API as a container

## Status

Accepted. Closes the first of ADR 0002's two deferred items ("Docker build +
image vulnerability scan. There is no Dockerfile for the app."). Depends on
ADR 0021, without which the image cannot serve a request.

## Context

The app has only ever run on the machine that built its corpus. Everything
that assumption hid had to be found before an image could work: ADR 0021 moved
the BM25 index off local disk, and the API had never configured logging at
all.

Two properties of this app shape the image more than anything else:

- **It carries a model runtime.** `torch`, `sentence-transformers` and two
  models are in the request path, for the embedder and the cross-encoder.
  `torch` alone is 553 MB of the 1.1 GB virtualenv.
- **It must never carry the documents.** `data/sbc/` is 983 MB of issuers'
  PDFs, kept forever and strictly local (ADR 0016, ADR 0019). An image that
  shipped them would break that, quietly, at a gigabyte a time.

## Decision

### The image runs the API, and nothing else

Ingestion, refresh and the reports stay on the machine that holds `data/`.
Nothing in the image fetches a PDF, and `.dockerignore` excludes `data/`.

**CI proves it rather than trusting it:** the built image is run and
`/app/data` must be empty. A `.dockerignore` regression is otherwise invisible
until an image is gigabytes too large.

### torch comes from PyTorch's CPU index, on Linux only

The default wheels bundle CUDA libraries that a CPU container cannot use.
`pyproject.toml` points `torch` at `https://download.pytorch.org/whl/cpu`
under `sys_platform == 'linux'`, so the image and CI get CPU wheels while
macOS development is untouched. Re-locking removed every `nvidia-*` package
and `triton`.

### Both models are baked in at build time

`SentenceTransformer` and `CrossEncoder` are instantiated during the build, at
the revisions `config.py` pins, into `HF_HOME=/opt/models`. The runtime sets
`HF_HUB_OFFLINE=1`.

- A cold start loads them from the image instead of downloading ~220 MB.
- **A HuggingFace outage cannot take the API down**, which it could if the
  first request fetched them.
- The pinned revisions are what ships, so the image is reproducible in the one
  way ADR 0008 noted was weak.

### One worker, several threads

Flask-Limiter has no shared storage, so each worker would keep its own
counters and the configured limits would multiply by worker count — the two
that matter being 5/min on register and 10/min on login. Until there is a
shared backend, the image runs **one** gunicorn worker.

Threads carry the concurrency instead, which suits this app: a request waits
on OpenAI and on Postgres, not on CPU. It also avoids paying for the model
runtime N times over in memory.

This is a real ceiling, not a preference, and it is the first thing to revisit
when traffic justifies a Redis backend for the limiter.

### Logs go to stdout in production

`setup_logging()` wrote only to a rotating file. In a container that
filesystem is ephemeral and nobody reads it. In production the root logger
also writes JSON to stdout, where the platform collects it; in development it
does not, so an ingestion run's log lines do not interleave with its own
progress output.

### Every image it depends on is pinned by digest

The base image, the `uv` image the build copies from, and the Trivy image that
scans the result are all pinned `name:tag@sha256:…`. A tag can be moved to
different bytes; a digest cannot. This is the same standard the repository
already applies to GitHub Actions (SHA-pinned) and to gitleaks (installed by
checksum), and the reason is the same: a build that is reproducible only until
someone else re-tags is not reproducible.

### It does not run as root, and does not write to itself

A `policypal` user owns the virtualenv and the source. `LOG_DIR` points at
`/tmp`. The image has no shell-accessible secrets: every setting comes from
the environment, and `.env.example` documents which ones with no values in it.

## Consequences

- **The image is 2.48 GB** — large by ordinary standards, and mostly the model
  runtime: CPU torch, and 217 MB of baked weights. Verified in the built
  image: `torch 2.14.0+cpu`, **zero** `nvidia-*` packages, no `ruff` or
  `pytest`, running as `policypal`, and `/app` holding only `src`,
  `migrations` and `alembic.ini`.
- **Proved rather than assumed.** A container with no `data/` directory
  (`Path('/app/data').exists()` is `False`) loads the BM25 index from Postgres
  and answers "What is a deductible?" with the glossary entry at 0.999,
  `HF_HUB_OFFLINE=1` throughout — so both models came from the image and no
  request touched HuggingFace. Served over HTTP it returns the right counties
  for a ZIP and 401 for an unauthenticated `/api/auth/me`, with access logs on
  stdout.
- **Building it is slow on a poor connection.** The model-baking step took
  about 7 minutes here, almost all of it downloading from HuggingFace
  unauthenticated. CI caches the layer, so it is paid once per lock or config
  change, not per build.
- **Cold starts load two models from disk.** Faster than downloading them, but
  not free; scale-to-zero trades latency for cost, and the deployment ADR
  decides that.
- **A model change is an image rebuild**, which is the point: the revision in
  `config.py` and the weights in the image cannot drift apart.
- **The scan runs on every PR** and fails on fixable HIGH or CRITICAL findings.
  A base-image CVE now breaks the build, which is the intended cost.
- **CD is still not built.** That is ADR 0002's second deferred item and the
  next decision.
