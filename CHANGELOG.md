# Changelog

## Unreleased

- Fix a whole class of silently-failing queries: a compound question scored
  far lower than either of its halves, because a cross-encoder asks "does
  this passage answer the *whole* query" and no single chunk answers both
  intents. "What does 'in-network' mean and why does it matter?" scored 0.487
  and returned nothing, while "What does in-network mean?" scored 0.993 — the
  corpus had held an authoritative definition the entire time. `search()` now
  reranks against a compound query's parts and keeps each chunk's best score,
  but only when the query as a whole matched nothing, so every query that
  already worked is untouched and the relevance gate isn't weakened (ADR 0004).
- Lower `rerank_top_k` from 15 to 5. Measured across 5/8/10/15: answered,
  evidence, and routing are identical at every value, so the extra ten chunks
  bought only citation noise (9.8 sources shown per answer versus 4.4) and 3x
  the context a small model has to stay grounded in.
- Fix the coverage eval measuring retrieval the application never performed:
  it called `search(top_k=5)` while the API resolved to `rerank_top_k` (15).
  Coverage now runs the configured production path.
- Add an abstention eval with its own floor. "Term life or whole life — which
  is better for a young family?" was listed as a corpus gap; it is not — the
  corpus answers the factual comparison at 1.00, and correctly returns nothing
  for a request for personalized advice. That eval case was wrong, and the
  abstention it was misreading is now asserted as a property, guarding the
  exact regression a widened retrieval would cause. Known limitation recorded
  in ADR 0004: abstention is not reliable for every advice-shaped question.
- Add `Umbrella insurance`, `Term life insurance`, and `Whole life insurance`
  to the Wikipedia corpus, closing gaps the coverage eval named.

Coverage: 16/20 -> 19/20 answered and with evidence; routing unchanged at
25/25. The one remaining gap is filing an auto claim.

- Add HealthCare.gov as a second corpus source and restructure ingestion
  around a `Source` abstraction (ADR 0003). The Wikipedia-only corpus scored
  25/25 on the retrieval eval while failing to answer 12 of 20 questions a
  real user would ask — the eval derived one question per ingested article,
  so it could only ever pass. It measured routing, never coverage.
  HealthCare.gov's content API (256 CMS Uniform Glossary terms + 436
  consumer articles, public domain under 17 U.S.C. § 105) covers what a
  policyholder *does*, where Wikipedia covers what insurance *is*.
  Unanswered consumer questions dropped from 12/20 to 4/20, with routing
  unchanged at 25/25 — so the ~4x larger, health-weighted corpus does not
  crowd out retrieval for the other lines.
- Rewrite `scripts/eval_retrieval.py` to measure coverage alongside routing,
  both with regression floors. Routing expectations now accept a set of
  acceptable sources: the old single-article form scored a real improvement
  as a regression, marking the authoritative glossary definition of
  "deductible" wrong for not being the Wikipedia article.
- Filter dated HealthCare.gov content on a moving cutoff — the feed still
  serves "Health coverage exemptions for the 2016 tax year only", and
  answering a live question with expired rules is worse than returning
  nothing. The cutoff is relative to the current date so it doesn't rot.
- Replace `download.py`/`clean.py` with `sources/wikipedia.py` and
  `sources/healthcare_gov.py` behind a common `Source` interface, and move
  shared chunking helpers to `chunking.py`. Adding a corpus is now one
  module plus one registry line; chunking, embedding, and the pipeline are
  untouched. Chunking strategy belongs to the source because shape differs —
  a glossary term is one atomic chunk (half a definition answers nothing),
  an article is split recursively.
- Add `html_text.py`: HTML→markdown via stdlib `HTMLParser`, so ingesting a
  content API adds no parsing dependency.
- Fix `chunk_id` collisions that the unique index would have caught mid-run:
  ids are now namespaced by source, and a title long enough to be truncated
  gets a digest suffix so two documents sharing a prefix can't clash.
- Fail with an actionable message when no source produces chunks, instead of
  an opaque division error from inside BM25Okapi.
- Raise the backend coverage floor from 80% to 85% (measured baseline is now
  88%), per ADR 0002's note to ratchet it as real coverage grows.

- Add a backend coverage floor to CI (`--cov-fail-under=80`), resolving the
  one item ADR 0002 had left deliberately open pending a baseline. Measured
  baseline is 81%, concentrated in the API/service layer; infrastructure
  glue wrapping torch/sentence-transformers sits lower by design and is
  exercised by `scripts/ask.py`/`scripts/eval_retrieval.py` instead.
- Harden the generation prompt against prompt injection (CLAUDE.md's LLM
  Top 10 mandate: treat model input as untrusted). The user's question and
  retrieved context are now wrapped in `<user_question>`/`<retrieved_context>`
  tags, the system prompt explicitly tells the model that content inside
  them is data to read and never instructions to follow (even instructions
  to ignore prior rules or reveal the system prompt), and any literal
  occurrence of those exact delimiter tags inside the question or context
  is stripped before insertion, so a message can't forge a fake closing tag
  and inject its own turn.
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
