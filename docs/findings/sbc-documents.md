# SBC documents — live ingests

**Verified:** 2026-09-19 (UTC), plan year 2026.
- Phase 2: New Hampshire and Delaware (all 13 counties), plus two Texas
  counties.
- Phase 3: the ten largest parent companies in FL, TX, NC, TN, AL and SC
  ([below](#phase-3-the-largest-issuers)).

**Referenced by:** [ADR 0013](../decisions/0013-sbc-documents.md),
[ADR 0015](../decisions/0015-sbc-at-scale.md), [Phase 2](../plans/phase-2-sbc-narrow-slice.md)
and [Phase 3](../plans/phase-3-sbc-top-issuers.md).
**Re-verify:** after any change to `src/ingestion/sbc/`, and every plan year.
Issuers change their layouts and hosts. What follows was observed on the date
above.

## How it was run

```bash
make ingest-plans STATES=NH,DE          # 13 counties, 0 failed
make ingest-sbc STATES=NH,DE,TX
```

- **156 distinct SBC URLs** sit behind 175 plans. Blue Cross and Blue Shield of
  Texas shares each document between two plans; every other issuer has one per
  plan.
- **130 were stored** and 26 blocked. None failed as `http_error`, `not_pdf`,
  `too_large`, `wrong_year` or `unparseable`.
- **A second run downloaded nothing.** The cache held 130 PDFs before it and
  130 after, none newer. Only the two refusing hosts were asked again, for
  their `robots.txt`.

## Per issuer

Sections are distinct template sections per document. All 25 is the full
template:

- 7 "Important Questions";
- 10 medical-event groups;
- 5 text sections: exclusions, other covered services, continuation rights,
  grievance rights, minimum essential coverage;
- 3 coverage examples.

| State | Issuer | SBC host | Plans | Documents | Stored | Sections |
| --- | --- | --- | --- | --- | --- | --- |
| DE | Ambetter Health of Delaware | api.centene.com | 17 | 17 | 17 | 25 |
| DE | AmeriHealth Caritas Next | www.amerihealthcaritasnext.com | 8 | 8 | 8 | 25 |
| DE | Highmark Blue Cross Blue Shield Delaware | shop.highmark.com | 15 | 15 | 15 | 25 |
| NH | Ambetter from NH Healthy Families | api.centene.com | 18 | 18 | 18 | 25 |
| NH | Anthem Blue Cross and Blue Shield | sbc.anthem.com | 12 | 12 | **0: blocked** | — |
| NH | Harvard Pilgrim Health Care | www.harvardpilgrim.org | 9 | 9 | 9 | 25 |
| NH | WellSense Health Plan | www.wellsense.org | 7 | 7 | 7 | 25 |
| TX | Ambetter from Superior HealthPlan | api.centene.com | 12 | 12 | 12 | 25 |
| TX | Baylor Scott and White Health Plan | wadcdnstorageprod.blob.core.windows.net | 9 | 9 | 9 | 25 |
| TX | Blue Cross and Blue Shield of Texas | www.bcbstx.com | 38 | 19 | 19 | 25 |
| TX | CHRISTUS Health Plan | chppayment.christushealth.org | 16 | 16 | 16 | 25 |
| TX | UnitedHealthcare | www.uhc.com | 14 | 14 | **0: blocked** | — |

- **3,254 chunks** in total. Most documents give one chunk per section. One
  Highmark section ran past the chunk size and was split in two.
- **Chunk size:**
  - the median is 103 tokens and the 95th percentile 241;
  - the largest is 384. The 350-token chunk size applies before the section
    heading is prepended.
  - Every chunk fits the cross-encoder's 512-token window with a question
    beside it.

## Blocked hosts

Both refuse `robots.txt` itself. That is read as "stay out", so the PDF is
never requested.

| Issuer | Host | Answer to `robots.txt` | Plans affected |
| --- | --- | --- | --- |
| Anthem Blue Cross and Blue Shield (NH) | sbc.anthem.com | HTTP 401 | 12 |
| UnitedHealthcare (TX) | www.uhc.com | HTTP 403 (CloudFront) | 14 |

Nothing works around either. Their plans get no SBC answers; answers link the
issuer's PDF instead (ADR 0014).

## Is each document the plan's?

- **Titles are no test.** An SBC's printed title rarely equals the catalog's
  `marketing_name`:
  - Ambetter's three issuers print only the issuer's name on page 1.
  - Baylor Scott & White prints the plan name without the catalog's marketing
    suffix, e.g. "(One free PCP visit, $0 Pediatric PCP visits)".
- **The HIOS plan ID was checked instead.** 8 of the 10 reachable issuers
  (95 documents) print it in the PDF: in the title, the footer or the SBC
  number. Every one matched a plan that points at that document.
- **The other two print no plan ID.** For Blue Cross and Blue Shield of Texas
  and CHRISTUS (35 documents), the printed title matches the catalog name.

## Spot checks against the PDF

Three documents were rendered and read by hand against the stored sections.
Each matched on:

- the overall deductible;
- the out-of-pocket limit;
- the "If you have a test" rows, including the imaging prior-authorization
  note;
- the "If you need immediate medical attention" rows.

| Plan | Deductible | Out-of-pocket limit | Imaging (in / out of network) |
| --- | --- | --- | --- |
| WellSense Clarity NH Bronze 6500 HSA | $6,500 / $13,000 | $10,600 / $21,200 | 40% coinsurance / not covered |
| Highmark my Blue Access Select PPO Bronze 3800 (DE) | $3,800 / $7,600 in network | $9,900 / $19,800 in network | 50% / 60% coinsurance |
| AmeriHealth Caritas Next Bronze Essential + No Referrals (DE) | $10,600 / $21,200 in network | $10,600 / $21,200 in network | no charge / not covered |

## Layout quirks the parser handles

The first run parsed every reachable document, but some headings came out
wrong. These were fixed before recording the counts above:

- **Highmark** draws a 6pt padding column at the left of some rows. The row's
  label then read as empty, and its heading landed in the row text. The label
  column is now taken from the table's other rows.
- **Several issuers print headings differently:**
  - wrapped: "out-of- pocket";
  - run together: "theout–of–pocket";
  - reworded: "Do I need a referral", "If you have mental health…".
  Headings are matched to the template's wording on letters alone, and a long
  heading may differ by a word or two.
- **Highmark** omits "Language Access Services". The minimum-coverage section
  now also ends at the template's "To see examples…" line, so it no longer runs
  into the coverage examples.

## Answering from them (ADR 0014)

Measured on 2026-09-19 (UTC), after the ingest above.

### Does the right section reach the model?

`plan_coverage` reranks all of a plan's sections with the cross-encoder and
passes the top 4 to the model.

- **The test:** 10 questions against 8 plans spread across the reachable
  issuers, such as "Is an MRI covered, and what does it cost?", "Is acupuncture
  covered?" and "Do I need a referral to see a specialist?".
- **Results:**
  - The right section was among the four for **78 of 80**, and ranked first
    for 65.
  - Both misses were one Blue Cross and Blue Shield of Texas plan, on MRI and
    on mental health. Its table text is interleaved across columns, and the
    coverage examples outranked the right section.
- **Scores are not answerability** (ADR 0004). The right section often scores
  well under 0.5, and the other three can score near 0. That is why no gate is
  applied.

### Evals

`scripts/eval_generation.py` was run three times:

| Set | Results | Floor |
| --- | --- | --- |
| COVERAGE | 6/6, 6/6, 5/6 | 5 |
| BOUNDARY | 2/2 each time | 2 |

The existing sets held their floors, with one exception: the plan-search case
that relies on a saved profile searched in 3 of 4 once. Measured directly, that
case searched 8/8 on this branch and 6/8 on `main`, so it is model variance and
predates this change.

### Context and tokens

| Question | Tokens per answer (all calls) | In context |
| --- | --- | --- |
| Definitional, e.g. "What is coinsurance?" | about 2,500 | 4 corpus chunks, 0 SBC passages |
| Coverage, with passages | 4,800 to 5,400 | 4 SBC passages; 0 or 1 corpus chunk |
| Coverage, blocked or missing SBC | about 4,000 | no passages; the answer links the PDF or asks |

- **Why coverage costs more:** a coverage answer adds a tool round.
- **SBC passages never take a corpus slot.** They arrive through the tool.
  Corpus chunks still come from the unconditional search, and a coverage
  question rarely clears its gate.

### Live checks through the route

These ran with a throwaway user (ZIP 03301), who was deleted afterwards.

- **Plan follow-up:** "What silver plans can I buy?", then "Does the second one
  cover MRIs?", cited the WellSense Silver 6000 imaging row (40% coinsurance,
  pre-authorization required) and linked its PDF.
- **Texas follow-up:** after a Texas search, "Does the first one cover MRIs?"
  cited the CHRISTUS plan's imaging row.
- **UnitedHealthcare (blocked host):** in the COVERAGE eval, not through the
  route, the answer says the SBC can't be read here and links its PDF.
- **Reload:** the sources survive it.
- **Phone width:** a long PDF link wraps (fixed during the check), and there
  is no horizontal scroll.
- **Leaks:** neither API key appears in any log, and the application log has
  no ZIP code. The Flask development server's own access log does record the
  query string of `/api/counties?zip=…` (ADR 0012's endpoint), so a ZIP appears
  there.
- **Known variance:**
  - The model sometimes adds the boundary sentence to a question about plan
    terms ("does it cover MRIs?"). That is harmless, but not asked for.
  - Before the prompt was tightened, "Will my MRI be covered?" asked right
    after a plan question could get no tool call. It was then declined by
    ADR 0010's no-grounding rule.

## Phase 3: the largest issuers

Measured on 2026-09-19 (UTC), plan year 2026, under ADR 0015.

### Choosing them

- **Source:** CMS's
  [2025 Issuer Level Enrollment PUF](https://www.cms.gov/marketplace/resources/data/issuer-level-enrollment-data)
  (sheet "QHP Enrollment Counts"), the newest published.
  - It gives each plan's average monthly enrollment, with state and HIOS issuer
    ID but no names. Plans whose count is suppressed (`*`, 252 rows) count as
    zero.
  - It includes Illinois, which left HealthCare.gov for 2026; Illinois is left
    out. That leaves 14,842,856 enrollees in the 30 states.
- **Names** come from `GET /issuers?state=…&year=2026`.
  - **It pages at 25, with no `total` field**, and takes an `offset`. A single
    call silently returns only the first 25 issuers of a state.
- **Parents** were assigned by issuer name and checked by hand:
  - "Ambetter …" is Centene;
  - "Anthem …" and "Wellpoint" are Elevance;
  - BCBS of Texas, Oklahoma and Montana are HCSC;
  - the two Florida Blue companies are GuideWell.
- **Aetna (sixth, 4.7%) withdrew for 2026.** None of its issuer IDs has a 2026
  plan in any of the eight loaded states.
- **2026 brought issuer IDs the 2025 data doesn't have.** After loading the
  catalog, every issuer whose name matches a top parent was compared with the
  list. Three were added:
  - Oscar Health Maintenance Organization of Florida (21525);
  - Oscar Insurance Company, Alabama (17091);
  - a second UnitedHealthcare, Texas (70754).
  Repeat this check whenever a new state or year is loaded.

### The catalog

`make ingest-plans`, one state at a time:

| State | Counties | Plans | Time |
| --- | --- | --- | --- |
| FL | 67 | 410 | 399 s |
| TX | 254 | 834 | 692 s |
| NC | 100 | 206 | 246 s, plus 237 s for the re-run |
| TN | 95 | 158 | 259 s |
| AL | 67 | 54 | 122 s |
| SC | 46 | 125 | 122 s |

- **The only failure:** one North Carolina county (37049) answered
  `/plans/search` with HTTP 500. A re-run of the state picked it up.
- **Scale:** the eight states now hold 1,873 plans and 36,040 plan–county rows.
  `find_plans` for a county, Miami-Dade (189 plans) included, took a median of
  5–26 ms over two measurements; the machine's load moves it more than the
  catalog does.

### What was read

| Parent | States with plans | Plans | Documents | Plans with an SBC | Why not |
| --- | --- | --- | --- | --- | --- |
| Centene (Ambetter) | all eight | 182 | 182 | 182 | |
| Oscar Health | AL, FL, NC, TN, TX | 180 | 180 | 0 | `robots.txt`: `Disallow: /` |
| UnitedHealth Group | AL, FL, NC, SC, TN, TX | 103 | 103 | 0 | `robots.txt` answers HTTP 403 |
| HCSC (BCBS of Texas) | TX | 546 | 25 | 546 | |
| Florida Blue | FL | 116 | 116 | 116 | |
| Molina Healthcare | FL, SC, TX | 46 | 46 | 46 | |
| Elevance (Anthem, Wellpoint) | FL, NH, TX | 46 | 46 | 0 | `robots.txt` answers HTTP 401 |
| BCBS of North Carolina | NC | 117 | 57 | 0 | a JavaScript bot challenge |
| BCBS of South Carolina | SC | 74 | 74 | 0 | `robots.txt`: `Disallow: /web/` |

Select Health sells only in Utah, which isn't loaded.

- **890 of the top parents' 1,410 plans (63%) have an SBC.** Four of the
  largest ten refuse automated requests, and one sits behind a bot challenge:
  - **Oscar** serves its SBCs from `d3ul0st9g52g6o.cloudfront.net`, whose
    `robots.txt` disallows every path to every agent.
  - **BCBS of South Carolina** serves them under `/web/…` on
    `www.southcarolinablues.com`, and its `robots.txt` disallows `/web/`.
  - **BCBS of North Carolina** redirects each link to `buyonline.bcbsnc.com`.
    That host answers every request, `robots.txt` included, with a 200 and an
    F5 JavaScript challenge page, not the PDF. It is stored as `not_pdf` and
    was not worked around. One more link returns a 404.
- **Nothing was worked around** (ADR 0013). These plans' answers link the
  issuer's PDF.
- **Phase 2's other issuers stayed covered:**
  - NH and DE were re-read for all issuers;
  - Baylor Scott & White and CHRISTUS in Texas were re-read with
    `ISSUERS=40788,66252`, which added the 3 documents their plans gained
    outside the two original counties.
  - In all, 436 documents are stored, with no orphan rows (a document no plan
    points at) and no `wrong_year`.

### Parsing

- **Speed:** 1.45 s per document on average; the tuning run took 794 s for 829
  documents, 369 of them stored.
- **Sections:** every stored document yields all 25 template sections, Florida
  Blue's and Molina's new layouts included.
- **One layout bug, fixed** (`PARSER_VERSION` 2). Florida Blue splits "If you
  have a hospital stay" across two left-column cells.
  - "If you have a" begins two template headings, so it stayed unresolved, and
    "hospital stay" became row text.
  - A label that continues an unresolved heading now completes it. This
    affected 9 documents.
- **Titles:** Florida Blue's printed title is read as the template's header
  line. Titles are stored but not used in answers.
- **Disk:** the kept PDFs of the tuning pass came to 321 MB (436 files,
  0.74 MB each).
- **The final run deleted them all,** as ADR 0015 then required. It read
  nothing already current, and left `data/sbc/raw/` empty.
  - It took 125 s for the top issuers, retrying failures only.
  - Most of that was BCBS of North Carolina's 57 links, requested again at
    two seconds each. Blocked hosts cost nothing, because their refusal is
    cached per run.
- **All 436 were then downloaded again, and are kept for good** (ADR 0016).
  - Run in the same three scopes, the downloads took 1,215 s, 129 s and 68 s.
    The file count only rose: 0, then 369, then 408, then 436.
  - **Every one is byte-for-byte the file first parsed:** its sha256 equals
    the one stored at the time. No issuer had changed a file.
  - `data/sbc/raw/2026/` now holds one PDF per stored document, 321 MB in all.
  - A further run would read only the failures (403 blocked, 56 `not_pdf`,
    1 HTTP 404) and none of the 436.

### Is each document the plan's?

- **231 documents print one of their own plans' HIOS IDs**, from Ambetter,
  Highmark, Baylor Scott & White, AmeriHealth, Harvard Pilgrim and WellSense.
- **None prints another catalog plan's ID.**
- **205 print no ID.** These are Florida Blue, BCBS of Texas, Molina and
  CHRISTUS. All 205 print their plan's catalog name on the first two pages,
  without the marketing suffix in parentheses and sometimes without the metal
  level ("BlueSelect 1443E" for "BlueSelect Silver 1443E").
- **Checked by hand against the rendered PDF** (deductible, out-of-pocket
  limit, and the rows below):

| Plan | Deductible (in network) | Out-of-pocket limit (in network) | Also checked |
| --- | --- | --- | --- |
| Florida Blue BlueSelect Silver 1443E | $4,000 / $8,000 | $8,100 / $16,200 | Imaging: deductible + 50%, prior authorization |
| Molina Bronze Enhanced 3500 (FL) | $3,500 / $7,000 | $9,950 / $19,900 | Imaging: 50%, not covered out of network |
| BCBS of Texas Blue Advantage Silver HMO 205 | — | — | ER: $1,000/visit plus 50% coinsurance |

### Does the right section reach the model?

Phase 2's method, on the new issuers: 10 questions × 20 plans, two each from
Florida Blue's two companies, Molina (FL, TX, SC), BCBS of Texas, and Ambetter
(FL, TN, NC, AL).

- **The right section was among the four passages for 200 of 200 pairs**, and
  ranked first for 170.
- Phase 2 measured 78 of 80. Plan-scoped retrieval reranks one document's ~25
  sections, so its quality does not depend on how many documents are stored.

### The general corpus is unaffected

- `chunks` still holds 1,568 rows. SBC text is only in `sbc_chunks` (ADR 0014),
  so general search, its gate and its eval floors see exactly what they did
  before.
- **No HNSW index.** The roadmap's trigger was a growing `chunks` table, and it
  did not grow. `search()` took a median of 200–315 ms over two measurements,
  most of it the cross-encoder.

### Evals

`scripts/eval_generation.py` was run three times, with four new COVERAGE
cases: Florida Blue lab work, Molina primary care, the BCBS of Texas ER, and a
blocked Oscar plan whose answer must link the PDF. The existing floors stayed
where they were, except COVERAGE, which is now 9.

| Set | Run 1 | Run 2 | Run 3 | Floor |
| --- | --- | --- | --- | --- |
| ANSWERS | 8/8 | 8/8 | 8/8 | 8 |
| REFUSALS | 4/4 | 4/4 | 4/4 | 4 |
| FOLLOW-UPS | 3/3 | 2/3 | 3/3 | 3 |
| PLAN SEARCH | 4/4 | 4/4 | 4/4 | 4 |
| COVERAGE | 9/10 | 9/10 | 10/10 | 9 |
| BOUNDARY | 2/2 | 2/2 | 2/2 | 2 |

- **All four new cases passed every run.**
- **Both COVERAGE misses were Phase 2's CHRISTUS imaging case.** Run alone it
  stated "no charge" in 3 of 6 tries; the answer names the preauthorization
  rule but not the price. The stored text is unchanged since Phase 2 and
  correct, but hard to read:
  - "Imaging (CT/PET scans," is on one line;
  - "No charge | Not covered" is on the next;
  - "MRIs)" follows.
  Writing each chart row as one sentence, as Phase 2's plan first proposed,
  would likely fix it. That is parser work for a later phase.
- **The follow-up miss was variance.** "What about for auto insurance?"
  declined once, then answered 6 of 6 when run alone. Nothing here touches the
  corpus or its prompts.
- **Tokens per coverage answer:** 2,431–5,628, a mean of about 4,500. That is
  as in Phase 2.

## Phase 4: every issuer, eighteen states

Run on 19–20 September 2026 against the 2026 plan year, from a clean `main`
with PRs #21–#26 merged. Ten states were added to Phase 3's eight, and every
issuer in all eighteen was read, not only the ten largest parents (ADR 0015,
"Phase 4's scope").

### The catalog

`make ingest-plans` one state at a time, 717 counties in **29 minutes**, with
**no county failing** in any state.

| State | Counties | Plan writes | Time |
| --- | --- | --- | --- |
| OH | 88 | 9,038 | 7m49s |
| MO | 115 | 4,970 | 4m02s |
| IN | 92 | 4,429 | 3m36s |
| OK | 77 | 3,724 | 3m04s |
| MI | 83 | 3,314 | 2m50s |
| MS | 82 | 2,834 | 2m30s |
| WI | 72 | 2,651 | 2m06s |
| LA | 64 | 2,218 | 1m50s |
| UT | 29 | 699 | 40s |
| AZ | 15 | 574 | 33s |

The ten states hold **1,403 plans behind 1,186 distinct SBC links**, and
**not one plan lacks a link** — the `no_link` status has no instance in any of
the eighteen states, so the eval case for it could not be written from live
data.

Compared against `top_issuers.py`, the new states' 74 issuers yielded exactly
**one** 2026 HIOS ID belonging to a listed parent: Oscar Health Plan, Inc.
(20635) in Mississippi. The other 41 unlisted issuers are genuinely separate
companies — Quartz, Priority Health, Medica, CareSource, the state Blues —
which is what "every issuer, not only the parents" was for.

### What was read

| | Phase 3 | Phase 4 |
| --- | --- | --- |
| States | 8 | **18** |
| Catalog plans | 1,873 | **3,276** |
| Issuers | 43 | **137** |
| Documents stored | 436 | **1,189** |
| Plans with a document read whole | 957 (51.1%) | **1,861 (56.8%)** |
| SBC sections | 10,904 | **29,763** |
| Disk | 321 MB | **947 MB** |
| Corpus chunks | 1,568 | **1,568** |

The corpus is the point of that last row: SBC text lives in `sbc_chunks` and
general search never reads it (ADR 0014), so tripling the documents changed
nothing about definitional questions.

**Why the rest have no document**, all eighteen states:

| Reason | Plans |
| --- | --- |
| `blocked` — the insurer refuses automated requests | 1,190 |
| `not_pdf` — a bot challenge answers the link | 115 |
| `http_error` — the link or the host fails | 88 |
| `partial` — read, but not all of the template | 22 |

- **Blocked stays blocked.** 1,190 plans, 36% of the catalog, behind hosts
  whose `robots.txt` disallows the path (483 documents), or that answer 403
  (375) or 401 (124). None was worked around (ADR 0013). 30 more are links
  HealthCare.gov gives as plain `http`, which the fetcher will not follow.
- **Paramount Healthcare (Ohio) fails TLS.** 26 documents end in
  `network error (SSLError)`: their certificate chain, not this code. Turning
  off verification to read an insurer's PDF is not a trade this project makes.

### Six ways a real PDF defeated the parser

Every one was found by running against 750 documents this code had never
seen. All six are fixed, with tests, and the parser went from version 3 to 9
— each bump re-reading every stored document **from disk, with no request to
any issuer** (ADR 0016).

| What | Who | Was | Now |
| --- | --- | --- | --- |
| No space characters in the font | 22 Health (FL) | 5 documents unparseable | read at a tighter word gap |
| Header drawn twice, letters alternating | BridgeSpan, Regence (UT) | refused as the wrong year | read once |
| "Beginning on or after 01/01/2026"; `01-01-2026` | Aspirus, McLaren, Network Health | refused as the wrong year | read |
| A NUL byte in the character map | Group Health Cooperative (WI) | **ended a 17-minute run** | stripped; a refused document no longer stops a run |
| A chart ruled across but not down | University of Utah (UT) | no chart at all | rows read from the bands between rules |
| A table header wrapped over two rows | BCBS Oklahoma (OK) | no chart at all | a label that begins a header counts as it |

44 documents had been refused as the wrong plan year although they were 2026.
That is the failure this phase most needed to find: a real document, dropped
quietly, with the plan's own prices in it.

### Documents read in part

`find_tables` returns nothing for a chart ruled across but not down, and some
issuers wrap a table's own header across two rows. Both left documents stored
as `ok` with no prices in them at all.

- **Rows are now read from the bands between horizontal rules** when a page
  has no findable table, and a label that *begins* a table's header counts as
  that header.
- BCBS of Oklahoma went from no chart to the full 25 sections; University of
  Utah from boilerplate alone to 9–12 of the chart's 10 groups.
- **The template's own closing sentence was being stored as a cost row.**
  "If your plan doesn't meet the Minimum Value Standards…" begins "If you"
  like the chart's ten groups do, so it was filed as one and then cited as
  though it were a price. The chart now ends there.
- **Partial documents fell from 62 to 22** of 1,189 (1.8%): 12 MedMutual
  missing 3 of the 7 Important Questions, and 10 University of Utah whose
  questions column interleaves its answers into the question text.
- Those 22 are recorded as `partial`, not `ok` (ADR 0017): their text is kept
  and searched, the plan card says the costs chart is not all there, and an
  answer that finds nothing says so rather than implying the plan excludes it.
- **A partial document usually still holds the words, under fewer headings.**
  Writing the eval case for one took three attempts: asked for its deductible
  it answered from a coverage example, and asked what it charges for mental
  health it answered from text that had landed under the hospital-stay
  heading. Only the seven Important Questions are truly absent from
  University of Utah's — "referral" appears nowhere in its stored text — which
  is what the eval case now asks about. The lesson for the status is the one
  ADR 0017 already takes: say what was read, and let the answer be judged on
  whether it can point at the words.

Measured again after every parser fix, the ranking is **identical**:
1,126/1,140 and 966/1,140, because the sections those fixes added rank where
they belong and the junk ones they removed never ranked at all.

### Is it still the right section, and the right plan?

- **Ranking, `scripts/eval_sbc_ranking.py`, 1,140 questions over 57 issuers:**
  the right section is in `plan_coverage`'s top 4 **1,126 times (98.8%)** and
  ranked first 966 (84.7%). Phase 3 measured 99.4% and 84.4% over a third as
  many issuers, so widening the corpus of documents cost 0.6 points of top-4
  and nothing at all of first place. The weakest issuer is BCBS of Oklahoma at
  16/20, whose chart this phase recovered.
- **Identity, 120 documents sampled:** 50 print a HIOS plan ID in the PDF, and
  **every one matched a plan that links it**. No document is filed under a
  plan that doesn't point at it.
- **Every stored file verified by hash** (`make sbc-report VERIFY=1`): 0
  missing, 0 changed.
- **No PDF was deleted at any point.** Every re-parse ran between two
  `stat` snapshots of `data/sbc/`; the only differences were files moved from
  `rejected/` back into `raw/` to be judged again, with their size and
  modification time unchanged.

### Latency

Measured with the SBC outer join in `find_plans` (ADR 0017), best of three:

| | |
| --- | --- |
| `find_plans`, Miami-Dade FL (189 plans) | 5.8 ms |
| `find_plans`, Harris TX (121) | 5.9 ms |
| `find_plans`, Cuyahoga OH (119) | 6.3 ms |
| `find_plans`, Maricopa AZ (86) | 5.4 ms |
| `search()`, corpus | ~255 ms |

The join is on the unique `(url, plan_year)` index and costs nothing
measurable.
