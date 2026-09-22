"""Turn an SBC PDF into the federal template's sections (ADR 0013).

Every Summary of Benefits and Coverage uses the same headings, so a section
is found by its heading, not guessed by length. Two steps:

- `read_pdf` is the only code that touches pdfplumber. It returns plain data:
  each page's text, the rows of its tables as (left-column label, rest of the
  row as text), and the coverage examples' three side-by-side columns.
- `parse_sbc` works on that data alone, so tests need no PDF.

A table's left column holds a group's label ("If you have a test"),
vertically centred in a merged cell. The rest of the group is rebuilt from
the table's ruled grid (ADR 0018): one line per service, its cells joined
with " | ", so a service name that wraps stays beside its price. A row with
no column rules is read as a band of layout text instead, its columns kept
apart with " | ".
"""
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path

import pdfplumber

# Stored with each document. Bump it when a change alters what `parse_sbc`
# yields for a real SBC: every stored document is then read again, and one
# is read again from its kept PDF (ADR 0016).
PARSER_VERSION = 9

# The template runs to about 8 pages; a file far beyond it is not an SBC.
MAX_PAGES = 30

# How far apart two characters must be to be different words. 3 points is
# pdfplumber's own default, stated here because the fallback below changes it.
WORD_GAP = 3
# Some issuers' PDFs hold no space characters at all, so every word boundary
# has to be inferred from the distance between letters, and this generator's
# gaps are narrower than the default. Used only for a document the default
# reading finds none of the template's sections in, so nothing that already
# parses can change.
TIGHT_WORD_GAP = 2

# "Coverage Period: 01/01/2026 – 12/31/2026", and the ways issuers vary it:
# "Beginning on or after 01/01/2026" (the template's own wording for a plan
# with no fixed period) and "01-01-2026".
_COVERAGE_PERIOD = re.compile(r"Coverage Period:[^\d\n]{0,40}\d{1,2}[/-]\d{1,2}[/-](\d{4})")
_TITLE = re.compile(r"^[:|\s]*(.+?)[\s|]+Coverage for:", re.MULTILINE)
_COLUMN_GAP = re.compile(r" {2,}")
# Control characters a PDF's own character map can yield. Postgres text cannot
# hold a NUL at all, and none of them are anything an SBC printed.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PAGE_FOOTER = re.compile(r"^(?:Page \d+ of \d+|\d+ of \d+)$")
# A left cell narrower than this is a table's padding column, not its labels.
_PADDING_WIDTH = 12
# Cell edges this close are one ruling line.
_SAME_EDGE = 1.5
# How much of a row a rule must cover to cut it: less is a box drawn inside a cell.
_FULL_RULE = 0.9
# The shortest word read as printed twice over itself; below it, "ll" would be one "l".
_MIN_DOUBLED = 6
# The shortest band between two rules that can hold a row of the chart.
_MIN_BAND = 6
# The shortest start of a table's own header read as that header ("Common").
_MIN_HEADER = 6

_QUESTIONS_HEADER = "Important Questions"
_CHART_HEADER = "Common Medical Event"
_EVENT_PREFIX = "If you"
# How alike a printed heading and the template's must be, letters only, and
# how long before likeness counts: short headings differ in a word that matters.
_HEADING_MATCH = 0.85
_MIN_FUZZY = 25
# The shortest start of a chart heading matched as its beginning ("If you need drugs to").
_MIN_PREFIX = 12
# Where the chart ends: the template's next headings, read as table rows too.
# "If your plan doesn't meet the Minimum Value Standards…" is the template's
# own closing sentence, not a chart row, but it begins "If you" like one.
_CHART_END = ("Excluded Services", "Services Your Plan", "Other Covered Services",
              "About these Coverage Examples", "This is not a cost estimator", "If your plan")
# The template's questions and chart rows as it words them. A printed heading
# is filed under the one it matches: issuers reword them slightly ("Do I need
# a referral"), wrap them ("out-of- pocket") and lose spaces ("theout–of–
# pocket"), and a page break can cut a chart heading short. One matching none
# is kept as printed.
QUESTION_HEADINGS = (
    "What is the overall deductible?",
    "Are there services covered before you meet your deductible?",
    "Are there other deductibles for specific services?",
    "What is the out-of-pocket limit for this plan?",
    "What is not included in the out-of-pocket limit?",
    "Will you pay less if you use a network provider?",
    "Do you need a referral to see a specialist?",
)
EVENT_HEADINGS = (
    "If you visit a health care provider's office or clinic",
    "If you have a test",
    "If you need drugs to treat your illness or condition",
    "If you have outpatient surgery",
    "If you need immediate medical attention",
    "If you have a hospital stay",
    "If you need mental health, behavioral health, or substance abuse services",
    "If you are pregnant",
    "If you need help recovering or have other special health needs",
    "If your child needs dental or eye care",
)
# An event's label can carry a note under its heading, e.g. where the
# formulary is: "If you need drugs… More information about…".
_EVENT_NOTE = re.compile(r"\s+(?=More information\b)")
# Every example ends with this line; what follows is page furniture.
_EXAMPLE_END = re.compile(r"^The total .+ would pay is .*$", re.MULTILINE)
_BULLET_GAP = re.compile(r"([•◼]) \| ")

# The three worked examples every SBC carries, side by side on one page:
# (text that finds its column, the name it is filed under).
COVERAGE_EXAMPLES = (
    ("Peg is Having a Baby", "Peg is having a baby"),
    ("Managing Joe", "Managing Joe's type 2 diabetes"),
    ("Simple Fracture", "Mia's simple fracture"),
)
_EXAMPLE_ANCHOR = "This EXAMPLE event includes"

# (section, its heading, the headings that can end it: whichever comes first).
# Headings are the template's own; an issuer that drops one simply yields no
# such section.
_TEXT_SECTIONS = (
    ("Services your plan does not cover", "Services Your Plan Generally Does NOT Cover", ("Other Covered Services",)),
    ("Other covered services", "Other Covered Services", ("Your Rights to Continue Coverage",)),
    ("Your rights to continue coverage", "Your Rights to Continue Coverage", ("Your Grievance and Appeals Rights",)),
    ("Grievance and appeals rights", "Your Grievance and Appeals Rights", ("Does this plan provide Minimum Essential",)),
    ("Minimum essential coverage and value", "Does this plan provide Minimum Essential",
     ("Language Access Services", "To see examples of how this plan")),
)


class SbcParseError(ValueError):
    """The file cannot be read as an SBC. The message names the reason, never content."""


@dataclass(frozen=True)
class TableRow:
    label: str      # the left column: a question, an "If you…" event, or blank
    body: str       # the rest of the row, as layout text


@dataclass(frozen=True)
class PdfPage:
    text: str
    rows: tuple[TableRow, ...] = ()
    # The coverage examples, one string per column, on the page that has them.
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class Section:
    heading: str
    text: str


@dataclass(frozen=True)
class SbcParse:
    title: str | None
    coverage_year: int | None
    sections: tuple[Section, ...]


def read_parsed(path: Path) -> tuple[list[PdfPage], SbcParse]:
    """A PDF's pages and the template's sections, read again at a tighter word gap if need be."""
    pages = read_pdf(path)
    try:
        return pages, parse_sbc(pages)
    except SbcParseError:
        spaced = read_pdf(path, word_gap=TIGHT_WORD_GAP)
        return spaced, parse_sbc(spaced)


def read_pdf(path: Path, word_gap: float = WORD_GAP) -> list[PdfPage]:
    try:
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise SbcParseError(f"{len(pdf.pages)} pages, more than an SBC has")
            if not any(page.chars for page in pdf.pages):
                raise SbcParseError("no text layer (a scanned image; not OCRed)")
            # dedupe_chars: some issuers print a second, offset text layer.
            return [_read_page(page.dedupe_chars(), word_gap) for page in pdf.pages]
    except SbcParseError:
        raise
    except Exception as exc:
        raise SbcParseError(f"unreadable PDF ({type(exc).__name__})") from exc


def _read_page(page, word_gap: float) -> PdfPage:
    return PdfPage(text=_band(page, page.bbox, word_gap=word_gap), rows=tuple(_table_rows(page, word_gap)),
                   examples=tuple(_example_columns(page, word_gap)))


def _band(page, bbox, layout: bool = True, word_gap: float = WORD_GAP) -> str:
    """The text whose characters sit inside `bbox`, one line per printed line.

    Selected by each character's midpoint, not `page.crop`: cropping clips a
    character to the box, so a line that touches the next cell would merge
    into that cell's line and interleave letter by letter.
    """
    x0, top, x1, bottom = bbox

    def inside(obj) -> bool:
        return (obj.get("object_type") == "char"
                and x0 <= (obj["x0"] + obj["x1"]) / 2 <= x1
                and top <= (obj["top"] + obj["bottom"]) / 2 <= bottom)

    text = _CONTROL.sub("", page.filter(inside).extract_text(layout=layout, x_tolerance=word_gap) or "")
    lines = (_COLUMN_GAP.sub(" | ", line.strip()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _table_rows(page, word_gap: float = WORD_GAP) -> list[TableRow]:
    """Each left-column cell of each table, with the rest of its row, top to bottom.

    A merged left cell spans every row of its group, so its band carries the
    whole group. pdfplumber can find a table again inside a larger one, so
    larger tables are read first and a cell inside one already read is skipped.
    """
    taken: list[tuple[float, float]] = []
    rows = []
    tables = sorted(page.find_tables(), key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]), reverse=True)
    if not tables:
        return _lined_rows(page, word_gap)
    for table in tables:
        x0, _, x1, _ = table.bbox
        left_cells = sorted((c for c in table.cells if abs(c[0] - x0) < 2), key=lambda c: c[1])
        label_edge = _label_edge(left_cells)
        for cell in left_cells:
            top, bottom = cell[1], cell[3]
            if bottom - top < 2 or any(t - 1 <= top and bottom <= b + 1 for t, b in taken):
                continue
            taken.append((top, bottom))
            edge = label_edge if cell[2] - cell[0] < _PADDING_WIDTH and label_edge else cell[2]
            label = " ".join(_band(page, (x0, top, edge, bottom), layout=False, word_gap=word_gap).split())
            body = _group_lines(table.cells, (edge, top, x1, bottom),
                                lambda box, layout: _band(page, box, layout, word_gap))
            rows.append((top, TableRow(label, body)))
    return [row for _, row in sorted(rows, key=lambda r: r[0])]


def _lined_rows(page, word_gap: float) -> list[TableRow]:
    """Rows for a chart ruled across but not down, so pdfplumber finds no cells.

    University of Utah Health Plans rules its chart with 20 horizontal lines
    and no vertical ones, so there is nothing to make a cell from and the
    whole chart was being lost. A row is then the band between two rules, and
    its label is whichever of the band's lines is one of the template's
    headings: ADR 0013's reading, kept for the layouts that defeat the grid.
    """
    rules = sorted({round(edge["top"], 1) for edge in page.edges if edge["orientation"] == "h"})
    x0, _, x1, _ = page.bbox
    rows = []
    for top, bottom in pairwise(rules):
        if bottom - top < _MIN_BAND:
            continue
        lines = _band(page, (x0, top, x1, bottom), word_gap=word_gap).splitlines()
        printed = next(((line, _heading_of(line)) for line in lines if _heading_of(line)), None)
        line, label = printed or ("", "")
        body = _join([other for other in lines if other != line])
        if label or body:
            rows.append(TableRow(label, body))
    return rows


def _is_header(label: str, header: str) -> bool:
    """Whether a row's label is a table's own header, printed whole or wrapped.

    BCBS of Oklahoma puts "Common" and "Medical Event" in rows of their own,
    so a label that begins the header counts as it.
    """
    return label.startswith(header) or (len(label) >= _MIN_HEADER and header.startswith(label))


def _heading_of(line: str) -> str | None:
    """The heading this printed line is, as the chart is read by it, or None.

    A table's own header wraps ("Common" above "Medical Event"), so a line
    that begins one is returned as the whole thing.
    """
    text = line.split(" | ", 1)[0].strip()
    if not text:
        return None
    if text.startswith(_EVENT_PREFIX) or _template_heading(text, QUESTION_HEADINGS) in QUESTION_HEADINGS:
        return text
    for header in (_CHART_HEADER, _QUESTIONS_HEADER):
        if _is_header(text, header):
            return header
    return None


def _group_lines(cells, bbox, read) -> str:
    """A group's rows, one line each: the service, then its cells, " | " between.

    `read(box, layout)` is the text inside a box. A row with no column rules
    is read as layout text, as the whole group was before (ADR 0018).
    """
    left, top, right, bottom = bbox
    inside = [c for c in cells if c[0] >= left - 1 and c[2] <= right + 1 and c[1] >= top - 1 and c[3] <= bottom + 1]
    lines = []
    for row_top, row_bottom in _row_bands(inside, left, top, bottom):
        edges = _column_edges(inside, left, right, row_top, row_bottom)
        if len(edges) < 3:
            lines.append(read((left, row_top, right, row_bottom), True))
            continue
        texts = (" ".join(read((a, row_top, b, row_bottom), False).split()) for a, b in pairwise(edges))
        lines.append(" | ".join(text for text in texts if text))
    return _join(lines)


def _row_bands(cells, left, top, bottom) -> list[tuple[float, float]]:
    """Where a group's rows begin and end: at each rule across the service column.

    A rule counts when it starts at the column's left edge and spans most of
    its width, padding cells included. Other columns can merge a cell across
    rows ("None" beside two services), and some issuers draw boxes inside a
    cell; neither ends a row.
    """
    firsts = [c for c in cells if abs(c[0] - left) < _SAME_EDGE and c[2] - c[0] >= _PADDING_WIDTH]
    if not firsts:
        return [(top, bottom)]
    column_right = Counter(round(c[2]) for c in firsts).most_common(1)[0][0]
    cuts = []
    for y in sorted({round(c[1], 1) for c in cells if top + 1 < c[1] < bottom - 1}):
        starting = [c for c in cells if abs(c[1] - y) < _SAME_EDGE]
        span = sum(max(0.0, min(c[2], column_right) - max(c[0], left)) for c in starting)
        if any(abs(c[0] - left) < _SAME_EDGE for c in starting) and span >= _FULL_RULE * (column_right - left):
            cuts.append(y)
    edges = [top, *cuts, bottom]
    return [(a, b) for a, b in pairwise(edges) if b - a > 2]


def _column_edges(cells, left, right, top, bottom) -> list[float]:
    """Where a row's cells begin: at each cell running most of the row's height."""
    height = bottom - top
    starts = {round(c[0], 1) for c in cells
              if c[0] > left + 1 and min(c[3], bottom) - max(c[1], top) >= _FULL_RULE * height}
    return [left, *sorted(starts), right]


def _label_edge(left_cells) -> float | None:
    """Where the table's label column ends: the right edge most of its real left cells share.

    Some issuers draw a thin padding column at the left of a row; that cell is
    not the label, and the label printed beside it belongs to this column.
    """
    edges = Counter(round(c[2]) for c in left_cells if c[2] - c[0] >= _PADDING_WIDTH)
    return edges.most_common(1)[0][0] if edges else None


def _example_columns(page, word_gap: float = WORD_GAP) -> list[str]:
    """The three coverage examples, cut apart at each column's left edge.

    Titles are centred, so they don't mark where a column starts; the
    template's left-aligned "This EXAMPLE event includes" line does, once
    per column.
    """
    titles = [page.search(title, x_tolerance=word_gap) for title, _ in COVERAGE_EXAMPLES]
    anchors = sorted(hit["x0"] for hit in page.search(_EXAMPLE_ANCHOR, x_tolerance=word_gap))
    if not all(titles) or len(anchors) != len(COVERAGE_EXAMPLES):
        return []
    top = min(hits[0]["top"] for hits in titles)
    edges = [page.bbox[0], *(x - 1 for x in anchors[1:]), page.bbox[2]]
    return [_band(page, (left, top, right, page.bbox[3]), layout=False, word_gap=word_gap)
            for left, right in pairwise(edges)]


def what_is_missing(parse: SbcParse) -> str | None:
    """What the federal template has and this reading doesn't, or None if it is whole.

    The questions carry the deductible and the out-of-pocket limit; the chart
    carries every price. A document without them was read but cannot answer
    what it is asked for, and ADR 0017 says that has to be visible.
    """
    headings = {section.heading for section in parse.sections}
    questions = len(headings & set(QUESTION_HEADINGS))
    events = len(headings & set(EVENT_HEADINGS))
    missing = []
    if questions < len(QUESTION_HEADINGS):
        missing.append(f"{len(QUESTION_HEADINGS) - questions} of the {len(QUESTION_HEADINGS)} questions")
    if events < len(EVENT_HEADINGS):
        missing.append("the whole costs chart" if not events
                       else f"{len(EVENT_HEADINGS) - events} of the {len(EVENT_HEADINGS)} chart's groups")
    return " and ".join(missing) or None


def _uninterleave(text: str) -> str:
    """The same text with any word printed twice over itself read once.

    BridgeSpan prints its header line as two overlapping runs, one bold, so
    the characters come back alternating: `CCoovveerraaggee PPeerriioodd::
    0011//0011//22002266`. A word is collapsed only when its characters pair
    up exactly, which no ordinary word of this length does.
    """
    words = (w[0::2] if len(w) >= _MIN_DOUBLED and w[0::2] == w[1::2] else w for w in text.split(" "))
    return " ".join(words)


def parse_sbc(pages: list[PdfPage]) -> SbcParse:
    """The template's sections, in reading order. Raises SbcParseError if it has none of them."""
    if not pages:
        raise SbcParseError("no pages")
    first = pages[0].text
    year = _COVERAGE_PERIOD.search(first) or _COVERAGE_PERIOD.search(_uninterleave(first))
    title = _TITLE.search(first)

    rows = [row for page in pages for row in page.rows]
    sections = [*_questions(rows), *_events(rows), *_text_sections(pages), *_examples(pages)]
    if not sections:
        raise SbcParseError("none of the template's sections found")
    return SbcParse(
        title=title.group(1).strip()[:300] if title else None,
        coverage_year=int(year.group(1)) if year else None,
        sections=tuple(sections),
    )


def _questions(rows: list[TableRow]) -> list[Section]:
    """The "Important Questions" table: one section per question.

    A question can wrap over several left cells, and the answer beside it can
    start above the question's first line, so rows collect until the label
    ends with "?", the template's form for every question.
    """
    sections = []
    label, body = [], []
    active = False
    for row in rows:
        if _is_header(row.label, _QUESTIONS_HEADER):
            active = True
            continue
        if _is_header(row.label, _CHART_HEADER):
            break
        if not active:
            continue
        if row.label:
            label.append(row.label)
        body.append(row.body)
        question = " ".join(label)
        if question.endswith("?"):
            sections.append(Section(_template_heading(question, QUESTION_HEADINGS), _join(body)))
            label, body = [], []
    return sections


def _events(rows: list[TableRow]) -> list[Section]:
    """The Common Medical Event chart: one section per "If you…" group.

    A page break can cut a group, and its label with it: the heading may
    start in the row text of one page and end as a label on the next. A row
    that doesn't open a group continues the one before it, and its label
    finishes the group's heading when that heading was left unresolved
    ("If you have a" above "hospital stay", each in a cell of its own).
    """
    sections: list[Section] = []
    active = False
    for row in rows:
        if _is_header(row.label, _CHART_HEADER):
            active = True
            continue
        if not active:
            continue
        first_cell = row.body.split("\n", 1)[0].split(" | ", 1)[0]
        if (row.label or first_cell).startswith(_CHART_END):
            break
        if row.label.startswith(_EVENT_PREFIX):
            heading, *note = _EVENT_NOTE.split(row.label, maxsplit=1)
            sections.append(Section(_template_heading(heading, EVENT_HEADINGS, prefix=True), _join([*note, row.body])))
        elif not row.label and first_cell.startswith(_EVENT_PREFIX):
            sections.append(Section(_template_heading(first_cell, EVENT_HEADINGS, prefix=True), row.body))
        elif sections and (row.label or row.body):
            last = sections[-1]
            joined = _template_heading(f"{last.heading} {row.label}", EVENT_HEADINGS, prefix=True)
            if row.label and last.heading not in EVENT_HEADINGS and joined in EVENT_HEADINGS:
                sections[-1] = Section(joined, _join([last.text, row.body]))
            else:
                sections[-1] = Section(last.heading, _join([last.text, row.label, row.body]))
    return sections


def _template_heading(printed: str, headings: tuple[str, ...], prefix: bool = False) -> str:
    """The template's heading that `printed` is, or begins if `prefix`; else `printed` as is.

    Compared on letters alone, so spacing, dashes and apostrophes don't count;
    a long heading may also differ by a word or two.
    """
    key = _letters(printed)
    if prefix and len(key) >= _MIN_PREFIX:
        for heading in headings:
            if _letters(heading).startswith(key) or key.startswith(_letters(heading)):
                return heading
    if len(key) >= _MIN_FUZZY:
        best = max(headings, key=lambda heading: SequenceMatcher(None, key, _letters(heading)).ratio())
        if SequenceMatcher(None, key, _letters(best)).ratio() >= _HEADING_MATCH:
            return best
    return " ".join(printed.replace("\u2019", "'").split())


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def _text_sections(pages: list[PdfPage]) -> list[Section]:
    text = "\n".join(
        line for page in pages for line in page.text.splitlines() if not _PAGE_FOOTER.match(line.strip())
    )
    # In template order, each heading searched for after the one before: the
    # combined "Excluded Services & Other Covered Services" line comes first
    # and would otherwise be taken for the second section's heading.
    sections = []
    cursor = 0
    for name, start, ends in _TEXT_SECTIONS:
        begin = text.find(start, cursor)
        if begin < 0:
            continue
        cursor = begin + len(start)
        stops = [stop for end in ends if (stop := text.find(end, cursor)) >= 0]
        body = text[cursor: min(stops, default=None)].strip(" :\n")
        if body:
            sections.append(Section(name, _BULLET_GAP.sub(r"\1 ", body)))
    return sections


def _examples(pages: list[PdfPage]) -> list[Section]:
    for page in pages:
        if page.examples:
            return [
                Section(f"Coverage example: {name}", _through_total(column))
                for (_, name), column in zip(COVERAGE_EXAMPLES, page.examples) if column
            ]
    return []


def _through_total(example: str) -> str:
    end = _EXAMPLE_END.search(example)
    return example[:end.end()] if end else example


def _join(parts: list[str]) -> str:
    return "\n".join(part for part in parts if part)
