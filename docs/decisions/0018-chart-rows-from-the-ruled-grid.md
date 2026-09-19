# 0018 — Chart rows read from the table's ruled grid

## Status

Accepted. Phase 4. Amends ADR 0013's "table cells are not rebuilt one by
one", and ADR 0015's "`parser_version` is NULL unless `ok`".

## Context

ADR 0013 read each "If you…" group of the SBC chart as one band of layout
text. That survived every issuer's cell splits, but it wrote a table row as
printed lines, not as a row:

- **A wrapped service name lost its price.** CHRISTUS prints "Imaging (CT/PET
  scans," then "No charge | Not covered", then "MRIs)". Asked about an MRI,
  the model stated the price in only 3 of 6 tries (Phase 3 findings).
- **Adjacent services interleaved** where cells wrapped differently, as in
  BCBS of Texas and Ambetter.

PDFs are now kept (ADR 0016), so a parser change re-reads every stored
document from disk, with no request to any issuer.

The template draws the chart as a ruled table, and pdfplumber returns its
cells. Rebuilding every cell was rejected in ADR 0013, because issuers merge,
split and inset cells differently. Measured on the 436 stored documents, the
table's structure is still usable if the rules are chosen carefully.

## Decision

### A group's rows come from the service column's rules

Inside one "If you…" group:

- **A row ends at a rule across the service column.** The rule must start at
  the column's left edge and span at least 90% of its width, counting a thin
  padding cell beside the service.
  - Rules in other columns don't count. Baylor Scott & White merges "None"
    across two services, and a full-width test missed that row end.
  - A box drawn inside a cell doesn't count either. CHRISTUS draws a box
    inside its padding whose line spans 91% of the column but starts inset.
- **A row's columns are the cells running at least 90% of its height.** Each
  cell's text is joined onto one line with `" | "`, and empty cells are
  dropped.
- **A row with no column rules keeps its layout text,** exactly as before.
  In the 18 issuers stored, that is the "Important Questions" table's wrapped
  rows; the chart itself reads from the grid.

The result is one line per service: `Imaging (CT/PET scans, MRIs) | No charge
| Not covered | Preauthorization is required…`.

`PARSER_VERSION` is 3.

### A PDF with no text layer is unparseable, with the reason

A scanned SBC has no characters to read. `read_pdf` refuses it as "no text
layer (a scanned image; not OCRed)", and the ingest report counts it.

There is no OCR. Misreading a digit in a dollar amount would be worse than
linking the PDF. OCR will be decided once Phase 4 measures how many there are.

### Every file the parser judged records which file and which parser

- `unparseable` and `wrong_year` rows now store the file's `sha256` and the
  `parser_version` that turned it down, as `ok` rows do. A later parser can
  judge the same file again, and the report can say which files a parser
  refused.
- `fetched_at` is when the PDF was downloaded: the file's modification time,
  kept by the atomic write and by moves. Before, it was stamped on every
  re-parse (ADR 0015's known limit). A failed fetch is stamped with the
  attempt's time.

## Consequences

- **Measured on the 436 stored documents:** all still yield their 25 sections.
  The ranking and eval results are in the Phase 4 findings.
- **Each parser bump costs a re-parse from disk,** about 1.5 s per document,
  and no download.
- **A merged cell's text lands in the row it is centred in.** A limitation
  shared by two services appears on one of them.
- **Layouts can still defeat the grid.** A group without rules falls back to
  the old reading, which is no worse than before.
