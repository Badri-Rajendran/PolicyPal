# Changelog

## Unreleased

- Add `scripts/eval_retrieval.py`: a small golden set of insurance
  questions (one per ingested article) run against the real corpus and
  real models, reporting top-5/top-1 accuracy. Unlike the mocked unit
  tests, this is the only thing that would catch a retrieval quality
  regression from a chunking/embedding/reranking change. Currently
  25/25 in the top 5, 24/25 ranked first.
- Harden CI supply chain: pin every third-party GitHub Action to its exact
  commit SHA (not a mutable version tag) and verify gitleaks' downloaded
  binary against its published sha256 checksum before executing it.
- Add rate-limit tests for every remaining API endpoint (previously only
  register had one) and close a few boundary/authz gaps CLAUDE.md's testing
  section calls for explicitly: login validation errors, thread
  title/message content length limits, and authz checks on the delete and
  post-message routes specifically (not just the one they share code with).
- Add CI (`.github/workflows/ci.yml`, ADR 0002): backend job runs ruff,
  Alembic migrations + drift check against a real pgvector service
  container, pytest, bandit, and pip-audit; frontend job runs lint, Vitest,
  build, and npm audit; a third job scans the full git history for
  committed secrets with gitleaks. Docker build/scan and Azure CD are
  deliberately deferred (no Dockerfile yet, no cloud credentials) — see
  the ADR.
- Add ruff, bandit, and pip-audit; fix everything they found (import
  hygiene, two dead shebangs, one justified broad `except`, two
  TYPE_CHECKING-guarded forward refs, three unpinned model revisions,
  one justified pickle-load suppression, three CVE'd transitive deps
  upgraded — torch, setuptools, tornado).
- Fix `chunks.chunk_id` schema drift: a plain index and a separate unique
  constraint had coexisted since the column was added, doing overlapping
  work the ORM model never asked for. Consolidated to the single unique
  index the model declares.
- Add lightweight contextual retrieval: index each chunk's text prefixed
  with its article title/section (a dead `contextualized_text` field was
  already scaffolded for this), so a chunk that never names its topic by
  itself still matches on keyword and semantic search. Raw chunk text
  stored/shown is unchanged.
- Wire `chunk_overlap`/`chunk_size` config into the actual chunker (they
  were previously hardcoded and silently ignored) and raise the default
  overlap to 50 tokens (~15%) so a definition and its qualifying clause
  don't get severed across a chunk boundary.
- Add the chat frontend (React 19, Vite): sign in/register, a thread sidebar,
  and a message transcript with footnote-style source citations. Design is a
  deliberate "policy document" identity (paper/brass palette, IBM Plex
  Serif/Sans) rather than a generic chat-bubble look.
- Add Vitest + React Testing Library; 75 tests across every component and
  hook (render, interaction, loading/empty/error states).
- Fix a real race condition found while browser-testing the new UI: sending
  the first message in a brand-new thread kicked off the message-history GET
  and the send's POST concurrently; the GET (fast, empty) would resolve
  after the optimistic user message was added and silently erase it. Fixed
  by never letting the fetch overwrite messages a send already added, with
  a regression test that reproduces the exact ordering.
- Update README to match the real stack and structure (Flask, plain JSX,
  actual folders and Make targets) — it had drifted to describe an
  unbuilt FastAPI/TypeScript/LangChain design.
- Add a Flask API: JWT auth (register/login/me) and chat endpoints (threads,
  messages) that run the RAG pipeline and persist the conversation.
- Add row-level authorization on chat endpoints — a thread not owned by the
  requester returns 404, never 403.
- Add rate limiting (Flask-Limiter) on every endpoint, tightest on auth.
- Add security headers and strict CORS (single allowed frontend origin) to
  the API.
- Add `docs/decisions/0001-chat-api-auth.md` recording the auth/API design.
- Fix the RAG generation prompt: source chunks were being sent to the LLM
  with an internal `Chunk ID` field it didn't need (citations already come
  back separately in the API response), and a missing separator glued the
  context and the "think step by step" instruction into one run-on line.
- Switch the local LLM to `Qwen/Qwen2.5-0.5B-Instruct` and cap
  `max_new_tokens` at 256 — the previous 1.5B model exceeded this machine's
  RAM and caused swap thrashing that looked like a hang.
- Only select float16 on CUDA; fall back to float32 on MPS, whose fp16
  generation kernels are unreliable.
- Fix `search()` dropping weakly-relevant chunks: add `min_relevance_score`
  and filter reranked results below it before they reach the LLM.
- Fix `tokenizer.apply_chat_template(...)` missing `return_dict=True`,
  which meant generation crashed on every real call.
- Fix a `logger.info` call with no `%s` placeholder that raised inside the
  logging module on every generation.
- Fix `environment` config typo (`"productin"`) that made JSON production
  logging unreachable.
- Add real pytest coverage for retrieval and generation (previously two
  argparse scripts with no `test_`-prefixed functions — pytest silently
  collected zero tests from them).
- Add `scripts/ask.py` as the one CLI entry point for manually exercising
  the RAG pipeline.
- Deduplicate the ingestion pipeline's four repeated print-block stages into
  a `STAGES` loop.
- Add `users`, `threads`, and `messages` tables.
