# Findings — California's SBC documents (2026)

Research for sub-project 2 of the California expansion (ADR 0026), done
2026-09-25 to 2026-09-26. CMS's California PUF has no SBC links, so each
carrier was researched on its own. This covers:

- where each carrier publishes its SBCs;
- what its `robots.txt` and website Terms allow;
- how each manifest row was checked;
- what was read.

Quotes from the Terms are verbatim, taken from the pages' own HTML, except for
L.A. Care's, which were never fetched.

## Per carrier

| Carrier (HIOS) | Plans | Access | Why |
| --- | ---: | --- | --- |
| IEHP (51396) | 5 | crawl | No website Terms found; `robots.txt` allows everything |
| Molina (18126) | 5 | crawl | Terms have no robots clause; `robots.txt` allows everything |
| Sharp (92499) | 9 | crawl | Terms have no robots clause; the SBC folder is outside the disallowed `/docs/default-source/pdfs/` |
| Balance by CCHP (47579) | 12 | crawl, **no 2026 links** | Only 2025 SBCs are published |
| Kaiser (40513) | 7 | manual | Terms ban robots |
| Blue Shield (70285) | 60 | manual | Terms ban robots |
| Western Health Advantage (93689) | 10 | manual | Terms ban robots |
| Anthem Blue Cross (27603) | 11 | manual | Terms ban robots |
| L.A. Care (92815) | 5 | manual | `robots.txt` names AI crawlers; Terms appear to ban robots |
| Valley Health Plan (84014) | 5, **2 linked** | manual | Host blocks bots; 3 of 5 SBCs not found |
| Health Net (67138) | 61 | disabled | SBCs only behind a POST search form |

Every entry has permission `mandated_disclosure` and `commercial_use =
"review"`. Nearly every carrier's Terms limit use to personal or non-commercial
purposes, or bar reproduction without written consent.

### What the Terms say about automated access

- **Kaiser**
  (<https://healthy.kaiserpermanente.org/termsconditions>, version 2.2,
  September 2026):
  - It is a material breach to use any "'deep-link', 'page-scrape', 'robot',
    'spider', data mining tools, data gathering and extraction tools, or other
    automatic device, program, algorithm or methodology, to (1) access,
    acquire, copy or monitor any portion of the Site".
  - Use is "solely for your personal, noncommercial use".
- **Blue Shield**
  (<https://www.blueshieldca.com/en/home/site-help/terms-of-use>): you may not
  "Attempt to access or search the site or content with any engine, software,
  tool, agent, device or mechanism other than software and/or search agents
  provided by Blue Shield of California or other generally available third
  party web browsers".
- **Western Health Advantage**
  (<https://www.westernhealth.com/legal/terms-of-use/>): "You may not ... (2)
  use any data mining, robots, or similar gathering and extraction tools". Its
  reproduction ban exempts "files containing Benefit Plans and Sales
  Materials". That may cover SBCs, but it is not relied on.
- **Anthem** (<https://www.anthem.com/ca/terms-of-use>):
  - You will not "(8) create a database by systematically downloading and
    storing this Application".
  - Nor "(9) use any robot, spider, site search/retrieval application or other
    manual or automatic device to retrieve, index, "scrape," "data mine" or in
    any way gather information from this Application".
- **L.A. Care** (<https://www.lacare.org/terms-and-conditions>): known only from
  search results, never fetched. These appear to ban "any robot, spider,
  scraper, or other automated means" and commercial use without written
  authorization.
- **Molina**
  (<https://www.molinahealthcare.com/members/common/en-us/terms_privacy.aspx>):
  there is no robots clause, but it says "You may use the Sites solely for the
  purposes of learning about (i) Molina Healthcare's health plans or (ii) other
  Molina Healthcare products or services."
- **Balance by CCHP** (<https://balancebycchp.com/terms-and-conditions/>): there
  is no robots clause. Content "may not be stored except for personal and
  non-commercial use. Republication and redissemination of Content is
  expressly prohibited without the prior written consent of Balance."
- **Sharp**
  (<https://www.sharphealthplan.com/terms-of-use-and-registration-agreement>):
  - There is no robots clause, only "not to misuse, abuse, or overuse beyond
    reasonable amounts, this website".
  - "Any reproduction or redistribution of this material beyond personal use
    is prohibited without the express written consent of Sharp Health Plan."
- **IEHP:** its only terms page covers its text-message service. The site
  footer reads "All Rights Reserved"; IEHP is a public entity.
- **Health Net:** robots are named only in a clause against flooding or
  disrupting the site. Downloads are "only for your personal, non-commercial
  informational purpose".
- **Valley Health Plan:** unknown. Both valleyhealthplan.org and the county file
  host (files.santaclaracounty.gov) answer automated clients with a Cloudflare
  403, `robots.txt` included.

## Where each carrier publishes, and how its rows were checked

- **IEHP.** Static PDFs are named by metal, e.g. `2026-Silver-70-SBC.pdf`, and
  listed at <https://www.iehp.org/en/browse-plans/covered-california>. The
  Silver 73/87/94 files are cost-sharing variants and are not used. Rows were
  checked by crawl: each prints "Inland Empire Health Plan: <metal> HMO", for
  2026.
- **Molina.** Files are named `CA26SBCE_<metal>_1.pdf`, beside the EOCs its
  member-forms page lists (the page lists only the EOCs). Checked by crawl:
  each prints "Molina Healthcare of California: <metal> HMO", for 2026.
- **Sharp.** Files are listed in the "2026 summary of benefits for Covered
  California" section of its 2026 plan-details page. **Each SBC prints its own
  HIOS plan ID** (`-01`), and every row matched. The 26793–26801 files are the
  off-exchange set.
- **Balance by CCHP.** On 2026-09-26 its media library held 2026 EOCs
  (`PY2026-EOC-OnX-IFP-*`) but only 2025 SBCs, which print coverage
  1/1/2025–12/31/2025. So no 2026 row is written. Its two plan sets differ
  only by service area (San Francisco and San Mateo).
- **Kaiser.** Files are named by HIOS variant, e.g.
  `40513CA0380003-01-en-2026.pdf`. All 7 `-01` files exist.
- **Blue Shield.**
  - There is no static PDF URL. The IFP document page
    (<https://www.blueshieldca.com/memberwebapp/welcome/documents/ifp>) opens
    `…/memberwebapp/unauth-document-download?fileName=<file>`, and that is the
    manifest link.
  - The Covered California files carry "(for Covered California)" and
    `ML`/`MI` form numbers.
  - **One Trio HMO SBC per metal serves all 18 regional plan IDs.** In the PUF,
    `70285CA80N000n` is rated only in rating area `n`, and nothing else differs
    between them.
  - The broker page's "Summary of Benefits" PDFs are California EOC summaries,
    not federal SBCs, and the parser rejects them.
- **Western Health Advantage.**
  - SBCs are generated from a query URL on `/shop/?sp=plan-sbc`. The `IE*`
    product codes are the Covered California ones, and `IM*` are off-exchange.
    With the wrong code, one line differs ("Minimum Value Standards").
  - Each metal's two plan IDs (rating areas 2 and 3) share one SBC.
- **Anthem.** The SBC posting site <https://sbc.anthem.com/dps> lists 52 CA
  Individual 2026 rows, but shows no URLs. The manifest's deep links follow
  the `dpsdeeplink` pattern the 30-state crawl already reads, built from each
  row's plan name, contract code and document ID. They are **inferred and
  unverified** until downloaded.
- **L.A. Care.** Five `la4307_lacc_sbc_*_en_202508.pdf` links were found in
  search results; one snippet shows coverage for 2026. **Unverified** until
  downloaded. The `la5600_laccd_*` files are its off-exchange line.
- **Valley Health Plan.** Gold 80 and Bronze 60 links are on the county file
  host, from search results, and **unverified**. The Platinum 90, Silver 70 and
  Minimum Coverage 2026 SBCs were not found; only "Schedule of Benefits"
  matrices turned up. Those three plans have no link.

### Requests made before the Terms were read

Kaiser, Blue Shield, WHA and Anthem were contacted by scripts before their
Terms had been read and the rule was set. Recorded for completeness:

- **Kaiser:** a ranged request for each of the 7 SBCs, and one full download
  on 2026-09-25.
- **Blue Shield:** its IFP document page, rendered once in a headless browser.
  No PDF was fetched.
- **Western Health Advantage:** its SBC pages, and the generated 2026 SBCs
  used to check the `IE*` codes.
- **Anthem:** the SBC posting site's search. No PDF was fetched.

None of these files is imported. `make import-sbc` reads only what a person
downloads in a browser.

## What was read (2026-09-26)

```text
make apply-sbc-manifest YEAR=2026
114 California plans for 2026 linked to 58 SBC documents; 76 not in the manifest, so shown with no link

make ingest-sbc STATES=CA YEAR=2026
58 SBC documents behind the CA plans for 2026; 0 already current, reading 19
39 awaiting a manual import (their host is manual-only)
19 ok
```

- **The 19 crawled documents all read `ok`:** 25 or 26 sections each, 6 to 14
  pages. `check-sbc-manifest` found no name mismatches.
- **`sbc-report STATES=CA`:** 19 of 190 plans read (10.0%), 95 awaiting import
  and 76 with no link. `VERIFY=1` found no missing or changed file.
- **`eval_sbc_ranking --year 2026`:** 1,303 of 1,320 in the top 4 (98.7%;
  floor 97%). IEHP, Molina and Sharp are 20/20 each.
- **A live question:** "What do these two plans charge for an urgent care
  visit?", asked about Sharp Silver 70 Performance HMO and Kaiser Silver 70 HMO.
  - Sharp is answered from its SBC ($50 copay, deductible does not apply),
    cited.
  - Kaiser, awaiting import, links its PDF.
  - The answer opens with the standard-version notice.

The manual carriers' counts are added here after their import.
