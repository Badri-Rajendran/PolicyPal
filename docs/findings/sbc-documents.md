# SBC documents — the first live ingest

**Verified:** 2026-09-19 (UTC), plan year 2026: New Hampshire and Delaware (all 13
counties), plus the two Texas counties already loaded.
**Referenced by:** [ADR 0013](../decisions/0013-sbc-documents.md) and
[Phase 2](../plans/phase-2-sbc-narrow-slice.md).
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
