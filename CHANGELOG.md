# Changelog

## Unreleased

### Added

- Conversation history, so a follow-up question means something. A follow-up
  is rewritten into a standalone question before retrieval — putting prior
  turns in the prompt alone does nothing, because retrieval runs first and the
  refusal fires before history is read (ADR 0005).
- Routes for every screen — `/login`, `/register`, `/chat`, `/chat/:threadId`
  — behind an auth guard, so a conversation is linkable and browser back works
  (ADR 0006).
- Session survives a reload: the token persists to `sessionStorage`, which
  keeps it out of disk storage and ends it with the tab.
- Multi-turn cases in `scripts/eval_generation.py`, with a floor of 2/3.
- Flask API with JWT auth (`register`/`login`/`me`) and chat endpoints for
  threads and messages, running the RAG pipeline and persisting the
  conversation (ADR 0001).
- `users`, `threads` and `messages` tables.
- React 19 + Vite chat UI: sign-in, thread sidebar, and transcripts with
  footnote-style source citations, styled as a policy document rather than a
  generic chat app.
- HealthCare.gov corpus source behind a `Source` abstraction — 256 CMS
  glossary terms and 436 articles. Wikipedia covers what insurance *is*, CMS
  what a policyholder *does*; unanswered questions 12/20 → 4/20 (ADR 0003).
- Moving-cutoff filter for dated HealthCare.gov content; the feed still
  serves 2016 tax-year rules, and expired rules are worse than no answer.
- `Umbrella insurance`, `Term life insurance` and `Whole life insurance` to
  the Wikipedia corpus, closing gaps the coverage eval named.
- `html_text.py`: HTML → markdown via stdlib `HTMLParser`, so ingesting a
  content API adds no parsing dependency.
- Contextual retrieval: chunks are indexed with their article title and
  section prefixed, so a chunk that never names its own topic still matches.
  Stored and displayed text is unchanged.
- `min_relevance_score` gate (0.5) on reranked chunks, so weak matches never
  reach the LLM.
- `scripts/eval_retrieval.py`: golden-set retrieval eval against the real
  corpus and models, with regression floors — 20/21 coverage, 25/25 routing.
- Abstention eval with its own floor (4/4), asserting that advice-shaped
  questions return nothing rather than a guess. ADR 0004 records that this is
  not reliable for every such question.
- `scripts/eval_generation.py`: grades the generated answer and refusal
  behaviour rather than retrieved context. Manual, not a CI gate — it
  generates once per question.
- `scripts/ask.py` as the single CLI entry point for exercising the RAG
  pipeline by hand.
- CI (`.github/workflows/ci.yml`): backend lint, migrations + drift check,
  tests, SAST and dependency audit; frontend lint, tests, build and audit;
  full-history secret scanning (ADR 0002).
- Backend coverage floor in CI, resolving the one item ADR 0002 left open.
- Vitest + React Testing Library; 75 tests covering render, interaction and
  loading/empty/error states for every component and hook.
- Rate-limit tests for every API endpoint, plus the boundary and authz cases
  CLAUDE.md calls for explicitly.
- pytest coverage for retrieval and generation — the previous argparse
  scripts had no `test_`-prefixed functions, so pytest collected zero tests.
- ruff, bandit and pip-audit.
- ADRs 0001–0004: chat API and auth design, CI scope, corpus sources, and
  retrieval tuning.
- Recorded the rejection of state insurance departments as a corpus source:
  their guides are copyrighted, and auto claims procedure varies by state, so
  one state's guide would be confidently wrong for most users (ADR 0003).
- `CLAUDE.md` and `frontend/CLAUDE.md` are now tracked; the repo's own docs
  already linked to them.

### Changed

- `rerank_top_k` 15 → 5. Retrieval quality was identical at 5/8/10/15, so the
  extra chunks bought only citation noise — 9.8 sources per answer down to
  4.4 (ADR 0004).
- Switched the local LLM to `Qwen/Qwen2.5-0.5B-Instruct` and capped
  `max_new_tokens` at 256; the previous 1.5B model exceeded available RAM and
  thrashed swap.
- Replaced the dead-end "not enough information" reply with one naming what
  PolicyPal covers and pointing to state insurance departments for what it
  deliberately doesn't.
- Rewrote `scripts/eval_retrieval.py` to measure coverage alongside routing,
  both with floors. Routing now accepts a set of valid sources — the
  single-article form scored a real improvement as a regression.
- Replaced `download.py`/`clean.py` with `sources/wikipedia.py` and
  `sources/healthcare_gov.py` behind a common interface; adding a corpus is
  now one module and one registry line.
- Raised default `chunk_overlap` to 50 tokens (~15%) so a definition isn't
  severed from its qualifying clause.
- Backend coverage floor 80% → 85%, tracking a measured baseline of 88%
  (ADR 0002).
- Ingestion now fails with an actionable message when no source produces
  chunks, instead of an opaque division error inside BM25Okapi.
- Deduplicated the ingestion pipeline's four repeated print-block stages into
  a `STAGES` loop.
- Renamed `self_relevant` to `matched_as_whole` in `search()` so the fallback
  condition reads plainly.
- Enabled the Alembic ruff post-write hook, commented out since before ruff
  was installed.
- Pointed the hatch wheel target at `src` instead of a `utils` package that
  never existed; `uv sync` was building an empty wheel.
- Rewrote the README to match the real stack — it had drifted to describe an
  unbuilt FastAPI/TypeScript/LangChain design.
- `.DS_Store` and `.claude/` are now ignored.

### Fixed

- An expired token surfaced as "Something went wrong." mid-conversation. A
  401, or a 422 carrying a JWT `msg`, on a request that sent a token now signs
  the user out and says why; a 401 without one stays a credentials failure.
- The frontend called `localhost:5000`, which on macOS resolves to `::1` and
  reaches AirPlay Receiver rather than Flask. It calls `127.0.0.1:5000` now.
- Comparison questions retrieved only one side, producing fabricated
  contrasts; a cross-encoder scores each chunk against the whole query, so one
  side took every slot. Now retrieved per intent (ADR 0004).
- Compound questions returned nothing: "What does 'in-network' mean and why
  does it matter?" scored 0.487 against the 0.5 gate, its first half 0.993.
  `search()` now falls back to reranking the parts (ADR 0004).
- The coverage eval certified that comparison failure as a pass — its
  evidence terms were satisfiable by one side alone. Comparison cases now
  require both sides named.
- The coverage eval measured a path the application never ran, calling
  `search(top_k=5)` while the API resolved to `rerank_top_k` (15).
- Frontend CI failed on every run: it pinned Node 20, but jsdom 30 and
  vitest 5 need ≥ 22.13. Now Node 24.
- A race condition erased the first message in a new thread — the history GET
  resolved after the optimistic message was added and overwrote it.
- `chunk_id` collisions the unique index would have caught mid-run; ids are
  now namespaced by source, and truncated titles get a digest suffix.
- `chunks.chunk_id` schema drift: a plain index and a separate unique
  constraint had coexisted since the column was added, now consolidated to
  the single unique index the model declares.
- `chunk_size` and `chunk_overlap` were hardcoded in the chunker and silently
  ignored.
- Generation crashed on every real call — `apply_chat_template(...)` was
  missing `return_dict=True`.
- A `logger.info` call with no `%s` placeholder raised inside the logging
  module on every generation.
- `environment` config typo (`"productin"`) made JSON production logging
  unreachable.
- float16 is now selected only on CUDA; MPS falls back to float32, whose fp16
  generation kernels are unreliable.
- The generation prompt sent an internal `Chunk ID` field the model didn't
  need, and a missing separator glued the context to the instruction.
- Import hygiene, two dead shebangs, a broad `except` and two forward refs
  surfaced by the new linters.

### Security

- Hardened the generation prompt against prompt injection (OWASP LLM Top 10):
  question and context are wrapped in tags the system prompt declares as
  data, and literal delimiter tags are stripped so a message can't forge one.
- Row-level authorization on chat endpoints — a thread not owned by the
  requester returns 404, never 403, so ids can't be enumerated.
- Rate limiting on every endpoint (Flask-Limiter), tightest on auth.
- Security headers and strict single-origin CORS.
- Pinned every third-party GitHub Action to a commit SHA, and verified the
  gitleaks binary against its published checksum before executing it.
- Pinned all three HuggingFace model revisions; upgraded three CVE'd
  transitive dependencies (torch, setuptools, tornado).

### Removed

- `src/core/chunking.py`, a 0-byte file shadowing the real
  `src/ingestion/chunking.py`.
