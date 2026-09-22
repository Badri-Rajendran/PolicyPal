# 0020 — An unavailable robots.txt is not a refusal

## Status

Accepted. Supersedes ADR 0013's "A refused `robots.txt` counts as disallowing
everything."

## Context

ADR 0013 read `robots.txt` before every SBC fetch and recorded a site that
refused it as `blocked`:

> A 401 or 403, on the file or on `robots.txt`, records the document as
> `blocked`. A refused `robots.txt` counts as disallowing everything.

That was written from two hosts in a two-state slice. At eighteen states it
governs **482 documents** — the second largest reason for missing coverage
after a real `Disallow` rule.

It is also stricter than the standard it implements. RFC 9309 §2.3.1.3 puts
every 400–499 status in one class, "Unavailable", and says a crawler **may**
access the site's resources; only §2.3.1.4's "Unreachable" (5xx) requires
assuming a complete disallow. A 401 or 403 on `/robots.txt` is a web server
declining to serve one file. It is not a statement about the documents.

The costs chart of this decision was never measured, so it was measured. All
482 documents come from **seven hosts**, so this is a census, not a sample:
one request each, two seconds apart, status and content type only, nothing
stored or parsed.

| Host | Documents | `/robots.txt` | The PDF itself |
| --- | --- | --- | --- |
| www.uhc.com | 229 | 403 | **403** |
| portal.medica.com | 117 | 403 | 200 `application/pdf` |
| sbc.anthem.com | 76 | 401 | 200 `application/pdf` |
| sbc.wellpoint.com | 34 | 401 | 200 `application/pdf` |
| apps.avmed.com | 14 | 401 | 200 `application/pdf` |
| www.mercyhealthsystem.org | 6 | 403 | **403** |
| static.mending.com | 6 | 403 | 200 `application/pdf` |

**Five of seven serve the document without objection.** The prediction going
in was the opposite — that a 403 on `robots.txt` meant a WAF refusing the
client outright, so the PDF would refuse too. That holds for exactly two
hosts, and they are already refusing on their own account.

## Decision

### The status of `robots.txt` decides, as RFC 9309 says

- **2xx** — these are the rules, parsed and obeyed. Unchanged: a real
  `Disallow` is still a refusal, and 483 documents remain blocked by one.
- **4xx** — "unavailable". No rules were published, and the fetch proceeds.
- **5xx** — "unreachable". A complete disallow, recorded as `robots.txt could
  not be served`. This is *stricter* than before, where any non-200 that was
  not 401/403 fell through to `allow_all`.

Nothing else moves. HTTPS only, public hosts re-checked at every redirect, two
seconds between requests to one host, the 15 MB cap, and the PDF check all
stand. **A 401 or 403 on the document itself is still `blocked`, and is still
never worked around** — which is what keeps UnitedHealthcare's 229 documents
and Mercy's 6 out, on their own servers' say-so rather than on an inference
from a different file.

### Why this is not a workaround

ADR 0013's rule stands on "as robots.txt conventions go", and the convention
it names is not the one the standard states. Reading the standard correctly is
not getting past a refusal; it is noticing that no refusal was made. The
project's rule — a host that says no is left alone — is unchanged, and the two
hosts that say no are still left alone.

The documents in question are Summaries of Benefits and Coverage, which
issuers are federally required to publish for exactly this audience. That is
context, not a licence: the deciding facts are the standard and the servers'
own answers.

### A network error still fails open, and is now logged

`requests` raising means we never learned anything. RFC 9309 would group that
with "unreachable" and disallow. It is left as it was, because changing it
would newly block hosts on a transient blip and that effect has not been
measured — but it now logs, instead of failing open in silence. Recorded here
rather than left implied.

## Consequences

- **247 documents behind 333 plans in 8 states** become readable, taking
  coverage from 1,940 plans (59.2%) to about 2,273 (69.4%) — the largest
  single gain available, and the only one that needed no parser work.
- **The reason a plan has no document gets more honest.** "The insurer blocks
  automated access" now means the insurer's server refused the document, not
  that it refused an unrelated file.
- **`robots.txt refused (HTTP 401/403)` disappears as a stored reason.** A
  refresh re-judges those documents; the ones that still refuse land on the
  document's own status.
- **A 5xx now blocks where it used to pass.** Rare, and the safer direction.
- **This is re-measurable.** Seven hosts, one request each — the same census
  can be re-run whenever the question comes up again.
