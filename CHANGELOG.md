# Changelog

## Unreleased

### Added

- Phase 4 live ingest: the catalog and SBCs for eighteen HealthCare.gov states
  — 3,276 plans from 137 issuers, every issuer's documents rather than the top
  parents'. 1,246 documents are stored and 1,940 plans (59.2%) have text behind
  them; the rest are named and counted, 995 of them blocked by their issuer.
  Six parser defects found in real PDFs were fixed along the way (ADR 0018),
  and the results are in `docs/findings/sbc-documents.md`.
- First refresh at full scale: 2,344 documents re-checked across all eighteen
  states (ADR 0019). 1,116 unchanged, 995 still blocked, 55 unreachable, and
  **18 that the issuer had replaced at the same URL** — the case nothing else
  would have noticed. Each superseded file moved to `data/sbc/archive/`, none
  deleted. Retrying past failures recovered 57 documents.
- Settled ADR 0018's deferred OCR question by measurement: **zero** of the
  documents read in eighteen states lack a text layer, so no issuer publishes
  a scanned SBC and OCR would buy nothing.
- A coverage answer names the plan it could not read even when that plan is
  the only one shown, and cites no glossary entry when asked what a plan does
  or charges. Measured over three runs, the MISSING DOCUMENTS set went from
  5, 3 and 4 of 5 to 5, 5 and 5.
- A document read in part is recorded as `partial`, not `ok` (ADR 0017): its
  text is kept and searched, but the plan card says its costs chart is not all
  there, and an answer that finds nothing says the part that would answer
  wasn't read here rather than implying the plan doesn't cover it. 22 of the
  1,246 documents stored are partial (new migration); the run first found 62,
  and the parser work that followed (versions 7 to 9) cleared 40 of them.
- `make refresh-sbc`: asks every stored SBC whether the issuer has changed it,
  with a conditional request, and retries recorded failures (ADR 0019). A
  changed file is downloaded and the one it replaces is moved to
  `data/sbc/archive/`, never deleted. `sbc_documents` gains `etag`,
  `last_modified` and `checked_at` (new migration).
- `docs/runbooks/sbc.md`: the monthly refresh, the plan-year rollover, what to
  do after a parser change, and the disk it all takes.
- `make sbc-report`: how much of the catalog has a Summary of Benefits behind
  it, per state and issuer, with the reasons for the rest, orphaned documents,
  plans the latest catalog run did not return, and the disk the kept PDFs use.
  `VERIFY=1` also hashes every kept PDF. It reads and writes nothing, and
  counts the versions a refresh replaced in `data/sbc/archive/` alongside the
  current ones.
- `make ingest-plans`, `make ingest-sbc` and `make sbc-report` take `YEAR=2027`,
  so a run during open enrollment does not default to the calendar year.
- `scripts/eval_sbc_ranking.py`: checks without calling a model that the
  section answering each of ten questions is among the four `plan_coverage`
  ranks highest, for two plans per issuer.
- Tests that no SBC ingestion code deletes a file, that `data/` stays in
  `.gitignore`, and that no PDF is tracked by git (ADR 0016).
- The plan table says, in each plan's row, whether its Summary of Benefits was
  read here and why not ("the insurer blocks automated access"), and counts
  beneath the table the plans it has none for. The link reads "Summary of
  Benefits (PDF)" and stays for plans that couldn't be read (ADR 0017). Cards
  saved before statuses were recorded show neither.
- Answers say which plans have no SBC text (ADR 0017). `search_plans` tells the
  model whether each plan's SBC can be read, `plan_coverage` gives the precise
  reason (no link, never read, blocked, not a PDF, wrong year…), and the prompt
  forbids describing such a plan from general material. Saved plan cards record
  the status in `message_plans.sbc_status` (new migration).
- MISSING DOCUMENTS eval set (full-marks floor), and coverage answers are now
  scored on their own text: citing general material, leaving an unreadable plan
  unnamed, or stating a figure with no document all fail. The scorer has its own
  tests.
- Phase 3 live ingest: the catalog for FL, TX, NC, TN, AL and SC, and the SBCs
  of the ten largest parent companies there. 436 documents are stored and 890
  of the top parents' 1,410 plans have an SBC; results are in
  `docs/findings/sbc-documents.md`.
- `make ingest-sbc ISSUERS=40788,66252` narrows a run to the HIOS issuer IDs
  given.
- Three 2026 issuer IDs of top parents (Oscar FL and AL, UnitedHealthcare TX),
  found by comparing the catalog with the list.
- COVERAGE eval cases for Florida Blue, Molina, BCBS of Texas and a blocked
  Oscar plan.
- `make ingest-sbc TOP_ISSUERS=1` reads only the ten largest parent companies'
  plans, by CMS's 2025 issuer-level enrollment (ADR 0015); the list is in
  `src/ingestion/sbc/top_issuers.py`.
- `sbc_documents.parser_version`: a document stored by the current parser is
  skipped on the next run, with no request and no parse.
- Coverage answers from a plan's SBC: a `plan_coverage` tool reranks that plan's
  own sections and cites the best four as "plan - Summary of Benefits - section"
  (ADR 0014). General search never sees SBC text.
- "The second one" resolves: the plans last shown in a thread reach the model as
  `<plans_shown>` (IDs, names, issuer, metal, year; no prices).
- Situational questions ("will my MRI be covered?") get a fixed boundary sentence
  and the plan's terms, never a yes or no.
- A plan whose SBC is blocked or missing gets a link to the issuer's PDF; https
  links in answers are clickable, through `safeUrl`, and wrap on a phone.
- COVERAGE and BOUNDARY sets in `scripts/eval_generation.py`, with floors.
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

- The BM25 index is stored in the database, in `search_indexes`, instead of
  `data/corpus/indices/bm25.pkl` (ADR 0021, new migration). A missing index
  was a `FileNotFoundError` nothing caught, so an app running anywhere but the
  machine that built the corpus answered no questions at all; it now raises an
  error naming the command to run. `make build-index` rebuilds it from the
  chunks already stored. Dropping the payload's unread `texts` key, a second
  copy of the corpus, took it from 3.4 MB to 1.8 MB.
- A `robots.txt` the server cannot serve is no longer read as a refusal
  (ADR 0020, superseding ADR 0013). RFC 9309 puts every 4xx in one
  "unavailable" class where a crawler may fetch, and probing all seven
  affected hosts found five serving their PDF at 200 `application/pdf`. A 5xx
  now disallows, which it did not before. A real `Disallow` rule, and a 401 or
  403 on the document itself, are still refusals and still never worked
  around. Refreshing the eight affected states took coverage from 1,940 plans
  (59.2%) to **2,274 (69.4%)**. Those documents parse less completely than the
  ones already read, so `partial` went from 22 to 138: the figure is 2,136
  whole documents and 138 partial, not 2,274 whole. No PDF was deleted; the
  archive grew by the 77 files issuers had replaced.
- The COVERAGE eval floor is full marks, 10 of 10, raised from 9. Parser
  version 3 reads CHRISTUS's wrapped imaging row as one line, so the answer
  states its price in 6 tries of 6, and the set ran 10/10 in three runs.
- `make ingest-sbc` no longer retries recorded failures; it reads what is new,
  what an older parser stored, and any stored document whose PDF has gone
  missing, and says how many failures it skipped (ADR 0019). Re-requesting a
  blocked host is now `make refresh-sbc`'s job, once a month.
- A document whose PDF carries no space characters, so that its text reads
  `SummaryofBenefitsandCoverage`, is read again at a tighter word gap
  (`PARSER_VERSION` 4, ADR 0018). It applies only to a document the normal
  reading finds no template section in, so nothing that already parses can
  change.
- A chart ruled across but not down is read from the bands between its rules,
  and a table header wrapped over two rows ("Common" above "Medical Event")
  still opens its table (`PARSER_VERSION` 7 and 8, ADR 0018). BCBS of Oklahoma
  and University of Utah were storing no costs chart at all.
- The federal template's closing sentence, "If your plan doesn't meet the
  Minimum Value Standards…", is no longer filed as a chart row and cited as
  though it were a price (`PARSER_VERSION` 9).
- A control character in a PDF's own character map is stripped from the text
  it yields. One Wisconsin document held a NUL byte, which Postgres text
  cannot hold at all, and it ended the whole run; a document the database
  refuses is now recorded as unparseable and the run carries on.
- The coverage period is read however the issuer prints it: doubled letters
  from a header drawn twice (`CCoovveerraaggee PPeerriioodd::`), the
  template's own "Beginning on or after 01/01/2026", and dashed dates
  (`01-01-2026`) — `PARSER_VERSION` 5 and 6, ADR 0018. 44 documents were being
  refused as the wrong year although they were 2026, and their text dropped.
  `make ingest-sbc` now judges a `wrong_year` file again when the parser has
  changed, reading the copy kept aside rather than asking the issuer for it.
- Chart rows are rebuilt from the table's ruled grid, one line per service
  (`PARSER_VERSION` 3, ADR 0018), so a wrapped service name stays beside its
  price. CHRISTUS's imaging row stated its price in 3 of 6 tries before and 6
  of 6 after. All 436 stored documents were re-parsed from disk, with no
  download, and still yield their 25 sections.
- A PDF with no text layer is recorded as `unparseable` with that reason; no
  OCR.
- `unparseable` and `wrong_year` documents keep the file's `sha256` and the
  parser version that turned them down, and `fetched_at` is now when a PDF was
  downloaded rather than when it was last parsed (ADR 0018).
- A coverage answer saves and shows only the corpus sources it cites; other
  answers keep every retrieved source (ADR 0017, amending ADR 0007).
- A parser fix reaches stored SBCs by bumping `PARSER_VERSION`, re-parsing
  them from disk, instead of re-parsing every document on every run (ADR 0015).
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

- The API never configured logging. Every command-line entry point calls
  `setup_logging()`; `create_app()` did not, so in the Flask process the root
  logger kept Python's default of WARNING with no handler: nothing the request
  path logged reached `logs/backend/app.log`, and the WARNING pins that keep
  the CMS api key out of `urllib3` and a user's ZIP and age out of `httpx` and
  `openai` were never installed.
- A signed, unexpired token naming no usable account returned 500. A subject
  that is not one of our IDs raised `ValueError`, and an account deleted since
  the token was issued left `get_current_user()` returning `None` for callers
  that dereference it. Both are now 401, so the client signs out cleanly.
- `make sbc-report` counted only `ok` as read, so it disagreed with the plan
  card, `search_plans` and `plan_coverage`, which all count `partial` too: it
  reported 1,918 of 3,276 plans covered where the rest of the app counts 1,940
  (59.2%). It also listed partly-read documents among the reasons a document
  could not be read, never hash-checked their kept PDFs under `VERIFY=1`, and
  left them out of the outdated-parser count. Ingestion likewise counted a
  current `partial` document as a recorded failure and told the operator to
  refresh it. All six sites now derive from `READ_STATUSES`.
- A thread whose history failed to load was shown as an empty conversation,
  suggested prompts and all, because the transcript had no error branch and
  fell through to the empty state. It now names the failure and offers to load
  the thread again.
- A follow-up question no longer fails when the rewrite model runs out of
  output tokens: the API's 400 ("max_tokens or model output limit was
  reached") now falls back to the raw query, as the rewrite already did for an
  empty or rambling reply.
- SBC parsing: a chart label split across two cells ("If you have a" above
  "hospital stay") now completes its heading instead of landing in the row
  text. `PARSER_VERSION` is 2.
- Downloaded SBC PDFs were deleted once their text was stored (ADR 0015), and
  Phase 3's final run removed all 436. Every downloaded SBC is now kept (ADR
  0016): no code path deletes one, a `wrong_year` file is moved to
  `data/sbc/rejected/`, and a stored document whose PDF is missing is
  downloaded again. `KEEP_PDFS` is gone. The 436 were downloaded again.
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
