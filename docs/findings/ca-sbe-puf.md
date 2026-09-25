# CMS state-based exchange PUF — California

What the file actually holds, checked against the real data before and after
the loader was written (ADR 0024). This is a record of observations on the
dates given, not a spec: CMS can change the file.

## Where it comes from

- **Page:** <https://www.cms.gov/marketplace/resources/data/state-based-public-use-files>.
  It covers 22 state-based exchanges, California among them, for plan years 2016–2026.
- **File:** `https://www.cms.gov/files/zip/californiasbpuf{year}.zip`, a US
  government work. cms.gov's `robots.txt` (checked 2026-09-24) disallows neither
  `/files/` nor `/cciio/`.
- **Publication dates:** 2026 data is dated 2026-06-03, 2025 is 2025-05-06 and
  2024 is 2024-05-14. There is **no 2027 file during 2027 open enrollment**.
- **The 2026 zip** (downloaded 2026-09-24): sha256
  `8a6d606a6da66b6d61296416d720f0d6b7a2766b398f52757f6ebe3600c52225`, 1,025,734
  bytes. It holds `CAPlans05052026.csv`, `CARates…`, `CAServiceAreas…`,
  `CABenefits…`, `CANetworks…` and `CABusinessRules…`. The CSVs are plain ASCII
  with no byte-order mark.

## Plans (`CAPlans`)

**Shape**
- 1,010 rows: individual and small group (SHOP), medical and dental.
- **Kept:** `MARKET COVERAGE = Individual`, `DENTAL ONLY PLAN = No` and
  `QHP NONQHP TYPE ID = On the Exchange`. That leaves 663 plan IDs, which are
  **190 base plans** (`STANDARD COMPONENT ID`) with their variants.
- **Variant suffixes:**

  | Suffix | `CSR VARIATION TYPE` |
  | --- | --- |
  | `-01` | `Standard <Metal> On Exchange Plan` |
  | `-02` | `Zero Cost Sharing Plan Variation` |
  | `-03` | `Limited Cost Sharing Plan Variation` |
  | `-04` | `73% AV Level Silver Plan` |
  | `-05` | `87% AV Level Silver Plan` |
  | `-06` | `94% AV Level Silver Plan` |

  There is no `-00` (off-exchange) row among the kept ones.

**Plan fields**
- **Metal levels** among the 190: Gold 46, Platinum 45, Silver 45, **Expanded
  Bronze 33**, Catastrophic 21. There is no plain "Bronze".
- **Plan types:** HMO, PPO, EPO.
- `ISSUER NAME` is **blank on every row**.
- `URL FOR SUMMARY OF BENEFITS COVERAGE`, `PLAN BROCHURE` and `FORMULARY URL` are
  **empty on every row**, and so is `NETWORK URL` in `CANetworks`.

**Cost sharing**
- `MEDICAL DRUG MAXIMUM OUT OF POCKET INTEGRATED` is `Yes` everywhere, so only the
  `TEHB … MOOP` columns hold values.
- The six in-network tier 1 individual columns hold only `$…` values (e.g.
  `"$5,200 "`, with a trailing space) or `""`.
- **Loaded:** 1,932 cost-share rows (four columns × variants, non-empty only).

**Issuers:** 11, named by hand in `src/ingestion/ca_puf/issuers.py`. Each HIOS ID
was matched by its network names and service-area footprint, e.g. 84014 sells
only in Santa Clara (Valley Health Plan), and 47579 only in San Francisco and San
Mateo (CCHP). This matches the 11 carriers Covered California announced for 2026;
Aetna left.

## Rates (`CARates`)

- 93,840 rows, including dental and small-group plans. **28,101** belong to the
  190 kept plans. That is 551 plan-area pairs × 51 age bands (`0-14`, 15 to 63,
  `64 and over`), with no duplicate or conflicting rate.
- `TOBACCO` is `No Preference` throughout: California does not rate tobacco.
- **156 of the 190 plans are rated in exactly one rating area.**
- **Spot check:** premiums shown by plan search for ZIPs 90012 and 90601 match
  `INDIVIDUAL RATE` to the cent. Examples:
  - L.A. Care Bronze 60 HMO, age 40: area 16 $367.43, area 15 $346.63.
  - Kaiser Silver 70 HMO, age 40, area 16: $481.83.

## Service areas (`CAServiceAreas`)

- Keyed by (`ISSUER ID`, `SERVICE AREA ID`). IDs such as `CAS001` repeat across
  issuers.
- **307 individual medical rows:**
  - 124 partial counties, with their ZIPs listed;
  - 5 `COVER ENTIRE STATE = true` rows, with a blank county.
- `COUNTY` looks like `Los Angeles - 06037`. All 58 California counties appear.

## Rating areas (not in the PUF)

The source is CMS's page
<https://www.cms.gov/cciio/programs-and-initiatives/health-insurance-market-reforms/ca-gra>.
It was transcribed into `src/ingestion/ca_puf/rating_areas.py` and checked
against the raw page on 2026-09-24.

- 57 counties map to areas 1–14 and 17–19.
- Los Angeles splits by ZIP prefix:
  - area 15: 906, 907, 908, 910, 911, 912, 915, 917, 918, 935
  - area 16: 900, 902, 903, 904, 905, 913, 914, 916, 923, 928, 932
- **909 is in neither list.** A web summary had put it in area 15.
- **Four Los Angeles ZIPs in CMS's 2026 crosswalk have an unlisted prefix:**
  90134, 90140 and 90189 (901), and 93063 (930, which spans Ventura County). The
  PUF's own partial-county lists include 901 ZIPs. These ZIPs have no area: their
  plans load and show unpriced.

## Where plans are sold

**Western Health Advantage (93689)** files one service area, `CAS001`, over
Marin, Napa, Solano and Sonoma (area 2) and Sacramento, Placer, El Dorado and
Yolo (area 3). Each plan is rated in one area only: `…0110001`–`…0120005` in
area 2 and `…0150001`–`…0160003` in area 3. Taking the service area alone would
offer each plan in four counties it has no rate for.

With "sold only where it has a rate for the county's area", the 2026 file
gives:
- **1,199 plan-county pairs kept, 40 dropped** (all Western Health Advantage);
- no plan sold nowhere;
- no plan rated in an area where it is not sold;
- all 58 counties served.

The loader enforces the last two, which a mistyped county in the map would break.

## Load of 2026 (2026-09-24, local database)

```
190 plans from 11 issuers, file 05052026: 1199 plan-county rows (40 dropped: no rate there), 28101 rates
Los Angeles ZIPs with no CMS rating area, shown unpriced: 90134, 90140, 90189, 93063
```

- `rating_areas`: 78 rows for 2026 (57 counties plus 21 Los Angeles prefixes).
- 310 plan-county rows list ZIPs.
- Reloading changes no row count; the 3,276 API-sourced plans are untouched.
