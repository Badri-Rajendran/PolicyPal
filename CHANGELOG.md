# Changelog

## Unreleased

### Added

- Plan documents: `make ingest-sbc STATES=...` reads each catalog plan's Summary of
  Benefits and Coverage into `sbc_documents` and `sbc_chunks`, one chunk per section
  of the federal template, kept apart from the corpus (ADR 0013).
- SBC fetching is polite and bounded: HTTPS public hosts only (re-checked on every
  redirect), `robots.txt` obeyed, per-host pacing, a 15 MB cap and a PDF check. A
  refusing host is recorded as `blocked`, never worked around.
- SBC ingestion is incremental: per-document transactions, a local PDF cache so a
  re-run downloads nothing it already has, a plan-year check, and a report naming
  plans left without an SBC.
- Dependency: `pdfplumber` (MIT), pinned and audited.
- Plan comparison table in the chat transcript: premium and the age it was
  priced for, deductibles (medical and drug when separate), out-of-pocket
  maximum, quality rating and a plan-summary link per plan, in a region that
  scrolls sideways on its own at phone width. Completes Phase 1.
- User profile: signup collects ZIP code, date of birth and (for a ZIP code in
  several counties) county, and `/profile` shows and edits them. Plan questions
  use the profile, filled in on the server, so the saved ZIP code and age never
  reach the LLM (ADR 0012).
- Nobody under 13 can sign up, and a refused signup stores nothing. A child's age
  asked about in chat prices that search but is never saved with its plans.
- `GET/PUT /api/profile` (owner only) and a public, per-IP rate-limited
  `GET /api/counties?zip=` for the signup form.
- Plan cards persist: `message_plans` stores each plan an answer showed as a
  snapshot (premium, the age it was priced for, deductibles, county, SBC
  link), and `MessageResponse.plans` returns them on both `POST` and `GET`
  (ADR 0011).
- `search_plans`: chat compares real Marketplace plans by ZIP code and age. The
  catalog filters by county, CMS prices the plans live for that age, and the
  model compares but never recommends (ADR 0010).
- `zip_counties` crosswalk, written by `make ingest-plans` for every state; a
  ZIP in several counties is asked about, never merged.
- Plan-search set in `scripts/eval_generation.py`, with a floor of 3/3.

- Plan catalog: `issuers`, `plans`, `plan_counties` and `plan_cost_shares`,
  loaded by `make ingest-plans STATES=...`. Relational, not vector — a
  deductible is a `WHERE` clause, not a similarity search (ADR 0009).
- Plan ingestion is idempotent and county-atomic: a re-run changes no row
  count, and a failed county is skipped rather than ending the run.
- ADR 0008: hosted LLM. Records why tool calling forced the move off Qwen
  0.5B, what stays local, and the costs — lost temperature control, pinned
  revisions, and PII egress — accepted along the way.
- Per-user daily token budget on generation. Flask-Limiter caps how many
  requests arrive, not what each one costs; an exhausted budget returns 429
  with `Retry-After` and an error string distinct from a rate limit.
- `docs/plans/`: phased roadmap for plan comparison — hosted LLM, Marketplace
  API catalog, then SBC ingestion. Records that the API covers ~7% of insured
  Americans, and that EOCs are unobtainable pre-purchase so SBCs replace them.
- Conversation history, so a follow-up question means something. It is
  rewritten into a standalone question *before* retrieval — history in the
  prompt alone changes nothing, since retrieval runs first (ADR 0005).
- Routes for every screen — `/login`, `/register`, `/chat`, `/chat/:threadId`
  — behind an auth guard, so a conversation is linkable and back works
  (ADR 0006).
- Session survives a reload: the token persists to `sessionStorage`, which
  keeps it out of disk storage and ends it with the tab.
- Multi-turn cases in `scripts/eval_generation.py`, with a floor of 2/3.
- `message_sources` table, so an answer keeps its citations when a
  conversation is reopened. `chunk_id` carries no foreign key — `make ingest`
  rebuilds the chunks table and would cascade the history away (ADR 0007).
- `make ui-dev`, `ui-build`, `ui-lint`, `ui-preview` and `ui-test`, wrapping
  every `frontend/package.json` script. Prefixed so a bare `make test` can't
  mean "Vitest only, pytest untouched".
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

- The ingestion user agent is one shared `USER_AGENT` constant.
- Chat layout columns are `minmax(0, 1fr)`: a plain `1fr` let a wide table widen
  the whole page on a phone.
- The token response's user carries `profile_complete`, but no profile values,
  so the ZIP code and date of birth stay out of `sessionStorage`.
- `.link` moved from `auth.css` to the shared `components.css`; three pages use it.
- `answer()` skips the model only when there are no chunks *and* no plan
  catalog, so a plan question reaches the tool. A reply grounded in neither a
  chunk nor a search is still refused.
- `answer()` and `answer_query()` return an `Answer` (text, chunks, plans,
  missing plan inputs) instead of a tuple.
- The Marketplace HTTP client moved to `src/core/marketplace_api.py`, shared
  by ingestion and chat.
- `urllib3`, `httpx` and `openai` loggers are pinned to WARNING; at DEBUG they
  would log the CMS key and a user's ZIP code and age.
- Refusal eval: "How much will my policy cost me?" became a car-insurance
  question — the plan tool now rightly asks for a ZIP code and age.

- The Claude review workflow is advisory (`continue-on-error`), not a merge
  gate. It authenticates through an external app-token exchange, so an
  expired token fails a PR whose lint, tests and scans are all green.
- `rerank_top_k` 15 → 5. Retrieval quality was identical at 5/8/10/15, so the
  extra chunks bought only citation noise — 9.8 sources per answer down to
  4.4 (ADR 0004).
- Answer generation runs on hosted `gpt-5-mini`, so Phase 1 can use tool
  calling. Embeddings and the reranker stay local, so ingestion and retrieval
  still cost nothing and work offline (ADR 0008).
- `max_output_tokens` is 512 and the rewrite cap 192: the cap bounds reasoning
  tokens as well as the reply, and at 48 the rewrite spent its whole budget
  reasoning and silently returned an empty string.
- No `temperature` — `gpt-5-mini` rejects it. Grounding rests on the system
  prompt and the 0.5 relevance gate.
- Query rewriting runs on `gpt-5-nano`, leaving `gpt-5-mini` for answering.
  Measured equivalent on follow-up resolution; nano reasons more per call, so
  it saves less than the per-token prices suggest.
- Generation eval floors raised to full marks — answers 7 → 8, follow-ups
  2 → 3, refusals unchanged at 4. Measured on the new models across three
  identical runs; retrieval floors were re-run and did not move.
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
  was installed, as an `exec` hook — ruff is a compiled binary and exposes no
  `console_scripts` entrypoint to discover.
- Pointed the hatch wheel target at `src` instead of a `utils` package that
  never existed; `uv sync` was building an empty wheel.
- Rewrote the README to match the real stack — it had drifted to describe an
  unbuilt FastAPI/TypeScript/LangChain design.
- `.DS_Store` and `.claude/` are now ignored.

### Fixed

- An OpenAI failure mid-request returned an HTML 500, dropped the user's
  own message, and lost whatever tokens had already billed. Now returns a
  JSON 502, keeps the message, and records the partial spend.
- An empty completion (output cap spent entirely on reasoning) was stored
  and shown as a real, blank answer. Falls back to the refusal message.
- Daily-budget exhaustion surfaced in the UI as "too quickly" — the same
  text as a rate limit — instead of the distinct message the API sends.
- `scripts/ask.py -t N` crashed with `'int' object is not reversible`. ADR
  0005 added `history` in the middle of `answer_query()`'s signature and this
  caller still passed `top_k` positionally into it.
- Citations vanished when a conversation was reopened — they were returned
  by `POST /messages` and never stored.
- The chat pane and the auth card were plain `div`/`section` elements, so
  neither page exposed a `main` landmark to skip to.
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

- Plan-summary links from CMS render only as `http(s)` URLs, never `javascript:` or
  `data:`, and open with `noopener noreferrer`.
- Composer discloses that messages and retrieved sources are sent to
  OpenAI, and asks users to avoid sharing identifying details (ADR 0008).
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
