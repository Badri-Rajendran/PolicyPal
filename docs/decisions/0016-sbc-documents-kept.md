# 0016 — Downloaded SBCs are kept

## Status

Accepted. Supersedes ADR 0015's "PDFs are deleted once their text is stored".
The rest of ADR 0015 stands: the top-issuer list, and parsing once per parser
version.

## Context

ADR 0015 deleted each SBC PDF once its text was stored, to save disk space and
to hold no issuer files. Phase 3's final run did exactly that: it removed all
436 downloaded documents, Phase 2's 130 among them, and left `data/sbc/raw/`
empty.

The project needs the source documents themselves, not only the text
extracted from them. For example:

- to re-parse after a parser change, without asking issuers again;
- to check a stored passage against the page it came from;
- to keep what an issuer published even after it changes or withdraws the
  file.

Disk is the cheaper resource. A PDF averages about 0.75 MB, so the 436
documents take roughly 330 MB.

## Decision

**No code path deletes a downloaded SBC.**

- **A parsed PDF stays** in `data/sbc/raw/<year>/`.
- **An unparseable PDF stays there too**, and is parsed again on the next run
  without a download.
- **A `wrong_year` PDF is moved aside**, to
  `data/sbc/rejected/<year>/<key>-<sha256 prefix>.pdf`, not deleted. ADR 0013
  wanted it out of the cache so that a corrected file at the same URL gets
  downloaded, and moving it aside does that too.
- **A stored document whose PDF is missing is downloaded again** on the next
  run. Every stored document therefore has its file.
- **`--keep-pdfs` and `KEEP_PDFS` are removed.** Keeping is the only
  behaviour.

This returns to ADR 0013's copyright posture:

- **files are kept strictly local**, in `data/sbc/`;
- they are never served, re-hosted, uploaded or committed;
- **`data/` stays in `.gitignore`, permanently.** The repository is public,
  and that entry is what keeps every downloaded file off it;
- answers quote briefly and link the issuer's own PDF.

## Consequences

- **Disk grows with the collection,** by about 0.75 MB per document. Budget
  for gigabytes as coverage grows.
- **A parser version bump re-parses from disk,** with no request to any
  issuer.
- **Restoring cost one download each.** The 436 deleted by ADR 0015 were
  downloaded again, politely paced. Each file's sha256 was compared with the
  one stored when it was first parsed; the result is in
  docs/findings/sbc-documents.md.
