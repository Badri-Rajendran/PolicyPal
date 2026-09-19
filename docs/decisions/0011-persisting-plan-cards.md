# 0011 — Plan cards are saved as snapshots

## Status

Accepted

## Context

After ADR 0010, `answer()` returns the plans a reply showed, and the chat
route dropped them. The API returned prose only, so a client had nothing to
draw a plan card from. A reloaded thread would be poorer than the live one,
which is exactly the gap ADR 0007 closed for citations.

## Decision

A `message_plans` table, one row per plan shown, cascading from its message.
`MessageResponse` gains `plans`, so `POST` and `GET` return the same shape.

### A snapshot, not a pointer into the catalog

Each row copies what was shown: name, issuer, metal level and type, premium,
deductibles, out-of-pocket maximum, rating, county, and the SBC link.

The alternative is to store `(hios_plan_id, plan_year)` and join to `plans`
at read time. It is smaller but gives the wrong answer:

- **The premium cannot be rebuilt.** It was priced live by CMS for one age,
  and neither the age nor the price is in the catalog.
- **The catalog moves.** A re-ingest overwrites premiums and cost shares in
  place, and a new plan year brings new rows. A join would show today's
  numbers beside yesterday's prose, which contradicts the answer they sit
  under.

### No foreign key to `plans`

For the reason ADR 0007 gives for `chunk_id`: a foreign key would either
block a catalog refresh or, with a cascade, silently delete conversation
history with it. `hios_plan_id` and `plan_year` are plain columns: a record
of what was shown, not a live reference.

### The age is stored; the ZIP code is not

`premium_age` records whose premium it is. Without it, a reloaded card shows
"$620.15/mo" with nothing to say it was for a 34-year-old, and misleads
anyone else of another age reading the thread. It is personal data, and it
is stored knowingly. The user's own message already holds the same age in
`messages.content`, so this adds no new kind of data. Like the rest of the
thread, it goes when the thread is deleted.

The ZIP code is not stored. The card names the county, which is what
decides which plans are sold and at what price, and is less identifying.

`premium_age` is null when CMS gave no live price. `monthly_premium` is
then null too, and `premium_reference` is the age-27 figure, so a reload can
never present a reference price as a live one.

### Row order is the order shown

`position` keeps the order the answer used, which is by live premium or by
deductible. The catalog cannot reproduce it. `(message_id, position)` is
unique, and its index also serves loading a message's plans.

### `needs_plan_inputs` is not saved

It was meant to drive an inline form asking for a ZIP code and age. The
user profile planned next (roadmap Step 5b) replaces that form, so it is
neither saved nor returned.

## Consequences

- **A reloaded thread is identical to the live one**, plan cards included,
  and each card stays true to the moment it was answered.
- **A card is history, not a quote.** A plan shown last month may since have
  changed price, or not be sold next year. Step 6's card should say when the
  plan was shown and link to HealthCare.gov for current prices.
- **Loading a transcript is three queries**: messages, their sources and
  their plans, each eager-loaded. Without the eager loads it would be one
  query per message per relation.
- **A plan answer writes up to ten rows.** Bounded by `SHOWN_PLANS`.
