# 0003 — Corpus sources: what PolicyPal ingests, and why

## Status

Accepted

## Context

The corpus was 25 Wikipedia articles (412K chars, 363 chunks). The retrieval
eval reported 25/25 top-5 and 24/25 rank-1, which looked like a solved
problem.

It wasn't. That eval derives one question per ingested article, so every
question is guaranteed to have an answer in the corpus — it can only ever
pass. It measures *routing* (does the right document come back), never
*coverage* (does the corpus hold an answer at all).

Probing the same corpus with 20 questions phrased the way a policyholder
actually asks:

| Outcome | Count |
| --- | --- |
| Nothing cleared the relevance gate | **12/20** |
| Weak match | 5/20 |
| Strong match | 3/20 |

Two of the three "strong" matches were confidently wrong: *"What is a
formulary?"* scored 0.96 against a chunk about preventive care that never
defines the word, and *"lower premium or lower deductible?"* scored 0.98
against a paragraph on a 2015 employer trend.

The cause is register, not volume. Wikipedia is excellent on what insurance
*is* — history, economics, how a line of business works. It contains almost
nothing on what a policyholder *does*: copay versus coinsurance, appealing a
denial, when a Special Enrollment Period applies. Those are the questions
PolicyPal exists to answer.

## Decision

### Ingest HealthCare.gov's content API as a second source

`https://www.healthcare.gov/api/{glossary,articles}.json` — 256 glossary
terms and 436 articles, served as JSON with no key or authentication. CMS
publishes it explicitly for reuse, and as a work of the US federal
government it is public domain under 17 U.S.C. § 105.

The glossary is the highest-value part. It is the CMS Uniform Glossary that
insurers are legally required to use in Summary of Benefits documents, so it
matches the vocabulary printed on a user's own paperwork — and its entries
are short and atomic, which is the ideal shape for a retrieval chunk.

**Chunking differs per collection, which is why chunking strategy belongs to
the source:** a glossary term is one chunk and is never split (half a
definition answers nothing), while articles are recursively split like
Wikipedia prose.

### Restructure ingestion around a `Source` abstraction

Every stage was hardcoded to Wikipedia — `download.wikipedia_data`,
`clean.wikipedia_data`, `chunk_wikipedia`, all looping over `WIKI_ARTICLES`.
Adding a second corpus by copying that shape would have doubled the
duplication.

`sources/base.py` defines the three things that genuinely differ between
corpora — `fetch`, `normalize`, `chunk_documents` — and nothing else.
Embedding and storage were already source-agnostic. Adding a corpus now means
one new module and one line in `sources/__init__.py`; no pipeline, chunking,
or embedding code changes.

`download.py` and `clean.py` are gone, folded into the sources that owned
their logic. Shared chunking utilities moved to `chunking.py` so a source can
build chunks without importing the orchestrator that imports it back.

### Filter dated content, on a moving cutoff

The feed still serves *"Health coverage exemptions for the 2016 tax year
only"*. A chatbot answering a 2026 question with 2016 rules is worse than one
that returns nothing, and this is the failure mode with real regulatory
consequence. Documents whose title names a year older than the previous one
are dropped. The cutoff is relative to the current date, not hardcoded, so
the filter does not rot; prior-year content is kept because prior-year tax
material is legitimately filed during the current year.

### Rewrite the eval to measure coverage as well as routing

Routing is kept — it catches embedding and reranking regressions. Coverage is
added: realistic consumer questions, scored on whether anything clears the
relevance gate and whether the retrieved text carries the evidence needed to
answer. Both have regression floors.

Routing expectations now accept a *set* of acceptable sources. The old
single-article form scored a real improvement as a regression: after this
change, *"What is a deductible?"* returns the authoritative glossary
definition instead of a Wikipedia paragraph, which is a better answer that
the old eval marked as a loss.

## Sources evaluated and rejected

| Source | Verified | Rejected because |
| --- | --- | --- |
| **Ask CFPB** (`/ask-cfpb/search/json/`) | Live, public domain | Genuinely useful for the lines HealthCare.gov can't reach (PMI, lender's vs. owner's title insurance, GAP) — but realistically only ~20–30 relevant entries, and it is a *search* endpoint, so a ranking change upstream would silently change the corpus. Revisit as a pinned, curated URL list. |
| **eCFR / govinfo** | Live | Regulatory legalese. Would bloat the corpus and make a consumer assistant answer in statute. Wrong register for the audience. |
| **OpenFEMA** | Live | Numeric datasets (claim counts, policy penetration), not explanatory prose. Wrong shape for RAG entirely. |
| **NAIC consumer guides** | — | No clear reuse license. Not worth the ambiguity given the project ingests and redistributes text. |
| **DOL / EBSA** (COBRA, ERISA) | — | PDF-only, no API. Real value, but adds a PDF-extraction dependency for content HealthCare.gov already largely covers. Revisit if the remaining gaps justify it. |
| **Medicare.gov** | Returns 404 | No public content API. |
| **State insurance departments** (CA DOI, TX TDI) | CA guides reachable | Rejected on two independent grounds — see below. |

### Why no source was added for auto claims procedure

The coverage eval's last gap is claims procedure, and it is a category rather
than one question: of ten claims questions probed, four returned nothing, and
every auto-specific one failed ("How do I file a claim after a car accident?",
"Do I need a police report?", "How do I dispute a low settlement offer?").

There is no federal equivalent of HealthCare.gov here, because auto insurance
is state-regulated. That leaves state insurance departments, and they fail on
two counts:

1. **Licensing.** California's guides carry an explicit "Copyright ©
   California Department of Insurance" notice. State works get no equivalent
   of 17 U.S.C. § 105, so the public-domain reasoning that justifies
   HealthCare.gov does not transfer. This is the same bar that ruled out NAIC.
2. **Correctness, which matters more.** Auto claims procedure varies
   materially by state — no-fault versus tort, statutory response deadlines,
   mediation rights. Ingesting one state's guide into an assistant with no
   notion of where the user lives would produce confident, specific, and
   wrong procedural advice for most of them. That is worse than returning
   nothing, and it is the same principle as the abstention set in ADR 0004.

Wikipedia does not fill the gap either: `Claims adjuster` documents the
profession, not the policyholder's process — no steps, documentation,
deadlines, or dispute guidance.

So the gap stays open deliberately. What changed instead is the response the
user gets: `NO_ANSWER_RESPONSE` now says what PolicyPal covers and names the
state insurance department as the authority for exactly these questions,
rather than dead-ending on "I don't know". Closing the gap properly needs
either state-aware retrieval or a nationwide source that does not yet exist.

## Consequences

Measured on the real corpus, before and after:

| Metric | Before | After |
| --- | --- | --- |
| Consumer questions with no answer | 12/20 | **4/20** |
| Consumer questions with answer evidence | — | **16/20** |
| Routing (top-5) | 25/25 | 25/25 |
| Chunks | 363 | 1549 |

Routing did not regress, so the ~4x larger health-weighted corpus does not
crowd out retrieval for auto, life, home, or the commercial lines. That was
the main risk of adding this much single-domain content, and it is the reason
the article set was ingested whole rather than curated by hand: the
hypothesis was testable, so it was tested rather than guessed at.

Four gaps remain, and the eval names them on every run rather than hiding
them:

- *"What does 'in-network' mean?"* — the glossary defines `In-network
  copayment` and `Network plan` but has no standalone entry for the term.
- *"How do I file a claim after a car accident?"* — auto claims procedure.
- *"Term life or whole life for a young family?"* — comparative life guidance.
- *"Do I need umbrella insurance?"* — no umbrella source in either corpus.

Three of the four are non-health lines, which is the shape of the next
source decision, not a defect in this one.

The corpus is now ~74% HealthCare.gov content, which makes PolicyPal's
answers materially US-specific. That matches what the sources authoritatively
support; it is a limitation to state in the UI rather than one to paper over
with lower-quality international content.
