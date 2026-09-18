# 0010 — One plan tool, and an early exit that no longer blocks it

## Status

Accepted

## Context

ADR 0009 put the Marketplace plan catalog in relational tables, but nothing
read them. `answer()` also returned the fallback whenever retrieval found no
chunks. A plan question such as "silver plans in 75801, I'm 34" matches no
corpus chunk, so it could never reach a model, let alone a plan tool. It is
the same shape as the bug ADR 0005 fixed: retrieval runs first, and gives up
before the later capability is consulted.

Premiums depend on age, and the catalog stores only CMS's age-27 reference
figure. Plans are sold per county, while users know their ZIP, and 28% of
ZIPs span more than one county.

## Decision

### Retrieval stays unconditional; the model gets one tool

Retrieval runs on every prompt, as before, and its chunks go into context.
The model may also call `search_plans(zip_code, age, metal_level, plan_type,
max_deductible, county_fips, sort_by)`. `search_corpus` is not a tool, because
retrieval has already run.

- **Offered only when the catalog has rows.** A corpus-only deployment keeps
  its prompt and its cost.
- **At most two search rounds.** The call after the last round sets
  `tool_choice: "none"`, so the model has to reply. There are no parallel
  calls, because strict schemas are not guaranteed for them.
- **A separate output cap after a search** (`plan_answer_max_output_tokens`,
  2048). A comparison of ten plans does not fit the 512 tokens a definitional
  answer uses.

### The early exit becomes two rules

1. **No chunks and an empty catalog:** return the fallback without calling
   the model, as before.
2. **No chunks and no search:** return the fallback even though the model
   ran. Nothing grounds what it wrote. The spend is still recorded.

So an off-topic question now costs one model call, about 1.3k tokens, when
the catalog is loaded, and is still refused. This was chosen over a keyword
pre-check. A missed phrasing there ("which one is cheaper?") would be a wrong
refusal, the very kind of bug this change removes.

### Premiums are live and age-rated, and sorted on the live figure

The catalog decides which plans are sold in the county and holds their
deductibles. CMS prices them: `POST /plans` with the candidate IDs and
`{"people": [{"age": age}]}`, in one call.

The candidate set is the 30 cheapest at age 27, the batch size verified
live, and the 10 shown are sorted on their live premiums. The obvious
alternative, scaling the stored premium by the age curve, is wrong. Verified
live, one issuer's plans scaled by ×1.118 where the rest scaled by ×1.1584,
so the age-27 order does not hold at 34
([findings](../findings/cms-marketplace-api.md), third pass).

- **A premium of 0 means "not priced here", never "free".** CMS answers a
  plan the county does not sell with `premium: 0` rather than an error.
- **A CMS failure is not a search failure.** The plans come back unpriced,
  and the model gives the age-27 figure labelled as a 27-year-old's. The call
  has an 8-second timeout (`cms_live_timeout_seconds`) and is not retried.
- **Catastrophic plans are left out from age 30** unless asked for by name.
  CMS prices them for anyone, but they are sold only to people under 30 or
  with a hardship exemption.

### ZIP to county is a table, and an ambiguous ZIP is asked about

`zip_counties` holds every ZIP–county pair for the plan year, written by
`make ingest-plans` from the county-zips payload it already downloads, for
all 59 jurisdictions. Rejected alternatives:

- **Reading the cached JSON:** it is an ingestion artefact and absent from a
  container.
- **A live `/counties/by/zip` call per question:** a second network
  dependency for data that is fixed for the year.

Keeping every state lets the tool say that an Illinois ZIP belongs to a state
running its own exchange, rather than that the ZIP is unknown. Because every
state's rows are written on each run, the plan year for a ZIP is the latest
one its own county has plans for. Otherwise, mid-rollover, a ZIP in a state
not yet ingested for next year would find nothing loaded.

A ZIP in several counties returns `ambiguous_county` with the county list.
The model asks the user, then searches again with `county_fips`. That
argument departs from the roadmap's signature, and is accepted only if it is
one of that ZIP's own counties. Merging the counties instead would list plans
the user cannot buy.

### The deductible shown is the one most buyers pay

This is the no-CSR, in-network, individual row: the combined medical and drug
deductible, or else the medical one. A plan with separate deductibles reaches
the model as `medical_deductible` and `drug_deductible`, never as a single
`deductible`. In a live run a plan with a $0 medical and a $5,500 drug
deductible was presented as a $0-deductible plan until the fields were named
this way. Only the "(Total)" out-of-pocket maximum has been observed, so
only that one is read. Otherwise the maximum is unknown, not guessed.

### The tool is a trust boundary

- **Arguments are untrusted** (LLM01). They are validated again with strict
  pydantic: a 5-digit ZIP, age 0–120, closed vocabularies, no extra fields.
  This happens before any query or outbound call, whatever the JSON schema
  promised.
- **Rejected values are never echoed or logged**, because one may be a ZIP.
- **A missing ZIP or age returns `needs_input`**, never a guess. That is also
  the hook for the form card in Step 6.
- **`run_tool` never raises.** An exception would escape the route's
  `openai.OpenAIError` handler and roll back the recorded spend.
- **Results are data only.** What to do for each status lives in the trusted
  system prompt, not in the result. Tool text passes through the same
  delimiter neutralization as retrieved chunks, since plan names come from
  CMS.
- **The tool is read-only and bounded** (LLM06, LLM10): at most two rounds,
  at most ten plans, and the daily token budget as before.

### Provenance and the return type

Chunks are cited as `[Source: …]` and plan facts as `[Plan: <id>]`.
`answer()` returns an `Answer(text, chunks, plans, needs_plan_inputs)` for
Step 5 to persist. It is a return value, not a ContextVar like the token
count, because a missed reset there would attach one user's plans to another
user's message.

## Consequences

- **A plan question costs more.** It takes two or three model calls and one
  CMS call. Across the scenarios run it measured 2.4k–5.4k tokens, against
  1.3k for a refusal.
- **The ZIP and age now leave the app twice**: to OpenAI in the prompt, as
  before, and to CMS in a request body. Neither is logged. `urllib3`, `httpx`
  and `openai` are pinned to WARNING, because at DEBUG they log the CMS URL
  with its key and the prompt with the ZIP and age.
- **`make ingest-plans` must be re-run** once on an existing database, to fill
  `zip_counties`.
- **The refusal eval changed one question.** "How much will my policy cost
  me?" is now correctly answered by asking for a ZIP and an age, so it became
  a car-insurance question. A plan-search set joins the eval, and a
  definitional question that searches plans counts as a miss.
- **Wording is still model variance.** The model sometimes offers to "show
  the rest" of a longer list, which it cannot do, although the prompt tells
  it not to. It may also skip `sort_by: "deductible"` for a deductible
  question. It then compares only the listed plans, and has said so. The
  data it cites is correct either way.
- **A plan outside the 30 cheapest at 27 can be missed** when it is cheapest at
  the user's age. The spread between issuers' age factors seen so far was
  about 3.5%, far short of that.
