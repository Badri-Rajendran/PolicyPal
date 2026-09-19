# 0012 — A user profile for plan search, and no minors' data

## Status

Accepted. Amends ADR 0011 on what a null `premium_age` means.

## Context

After ADR 0010, `search_plans` took its ZIP code and age from the model,
which read them from the conversation. The user had to type both into every
plan question, and both went to OpenAI in the prompt each time. The product
direction is to collect them once at signup, show and edit them on a profile
page, and answer plan questions from the profile.

That puts personal data into the `users` table for the first time, beyond an
email address. It also raises a question the chat alone never did: what
happens when the person is a child.

## Decision

### Signup collects ZIP code, date of birth and county

- **ZIP code and date of birth are required.** A county is required only when
  the ZIP code spans several (28% do), chosen from `zip_counties`. The signup
  form fetches the choices from `GET /api/counties?zip=`.
- **Date of birth, not age.** An age entered once goes stale, and premiums
  rise with it. The age is computed whenever a search runs.
- **Any real US ZIP code is accepted**, including one in a state that runs its
  own exchange. Insurance Q&A works for everyone. The form says once that plan
  comparison isn't available there, and plan search explains it.
- **Accounts from before this change are nudged, not blocked.** The columns are
  nullable. Chat works as before, a banner links to the profile page, and a
  plan search with no profile asks for one.

### Nobody under 13, and nothing stored about them

13 is COPPA's line: collecting personal data from a child under 13 needs
verifiable parental consent, which this app has no way to obtain.

- **The age check runs before anything is written.** `validate_profile`
  refuses a date of birth under 13 before `register_user` creates the row, so a
  refused signup stores nothing, and nothing logs the date. The form runs the
  same check first, so an under-13 date is normally never even sent.
- **"Today" is the earliest date on Earth (UTC−12).** On a UTC server, a
  12-year-old in Hawaii would count as 13 for up to eleven hours before their
  birthday arrived locally. Measuring in UTC−12 means an account is only ever
  created once the person is 13 in every US time zone. It can accept someone
  up to a day late, never early.
- **A child's age in a question is used once.** "Plans for my 10-year-old"
  needs the age to price the search, so it goes to CMS for that call. The saved
  plan card then drops it: `premium_age` is stored only at 13 and over, and
  the card reads "for the age you asked about". The question itself is saved
  as typed, as every message is. Reliably removing ages from free text isn't
  possible, and a pattern that tried would miss some and mangle others.

**This amends ADR 0011.** There, a null `premium_age` meant "not priced".
Unpriced is now told by `monthly_premium` being null; a null age next to a
price means the age was a child's.

### The profile is filled in on the server, never in a prompt

`answer_query(..., profile=)` passes a `PlanProfile` (ZIP code, age computed
now, county) through to `run_tool`, never into a message.

- **Null arguments take the profile.** The model sends `search_plans` with
  `zip_code` and `age` null, and the server fills them in.
- **A question's values apply to that search only.** A ZIP code or age the
  question names ("for my mother, 60") overrides the profile for that one
  search and never changes it.
- **The saved county applies only to the saved ZIP code.** Another ZIP code
  resolves its own.
- **The model sees the county name in results, never the ZIP code or age.** It
  says "for your age".

This follows CLAUDE.md's "keep secrets and PII out of prompts": the saved ZIP
code and age now never reach OpenAI. Values the user types into a question
still do, because they are part of the question.

### Who can read the profile

- **`GET` and `PUT /api/profile`** need a token and act on the caller only.
  They are limited to 60 and 10 per minute. Validation errors name the field
  and never echo the value.
- **The token response carries only `profile_complete`.** The browser keeps
  that response in `sessionStorage`, so the ZIP code and date of birth stay
  out of it. The profile page fetches them when it opens.
- **`GET /api/counties` is public**, because signup comes before an account.
  It serves only CMS's public ZIP-to-county crosswalk, limited to 30 per
  minute per IP address.
- **At rest, the columns are plain.** They rely on the database's storage
  encryption: Azure Database for PostgreSQL encrypts at rest by default. There
  is no column-level encryption. That is a deliberate choice for this stage,
  stated here rather than implied, and worth revisiting if the profile grows
  more sensitive fields.

## Consequences

- **Plan questions no longer need a ZIP code or age typed in**, and the saved
  ones never reach the LLM provider. The eval gains a profile-only case whose
  prompt holds neither.
- **Signup is longer**: three fields, a fourth for a multi-county ZIP code.
  This is the price of plan answers without asking.
- **`zip_counties` must be loaded before anyone can sign up**, since the ZIP
  code is checked against it. `make ingest-plans` fills it on any run, for
  every state.
- **Every API test registers with a profile.** The fixtures seed a small ZIP
  crosswalk in each test transaction.
- **An age is computed as of today**, not the coverage start date CMS rates
  on. Close to a birthday, a premium can be one age band off. HealthCare.gov
  gives the price for the actual start date.
