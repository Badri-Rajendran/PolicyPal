"""Turn an SBC PDF into the federal template's sections (ADR 0013).

Every Summary of Benefits and Coverage uses the same headings, so a section
is found by its heading, not guessed by length. Two steps:

- `read_pdf` is the only code that touches pdfplumber. It returns plain data:
  each page's text, the rows of its tables as (left-column label, rest of the
  row as text), and the coverage examples' three side-by-side columns.
- `parse_sbc` works on that data alone, so tests need no PDF.

Table cells are not rebuilt one by one. Issuers wrap and split cells in
different places, and a row's label is vertically centred in a merged cell,
so the rows of one "If you…" group are read as one band of text. The band
keeps each line's columns apart with " | ".
"""
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path

import pdfplumber

# The template runs to about 8 pages; a file far beyond it is not an SBC.
MAX_PAGES = 30

_COVERAGE_PERIOD = re.compile(r"Coverage Period:\s*\d{1,2}/\d{1,2}/(\d{4})")
_TITLE = re.compile(r"^[:|\s]*(.+?)[\s|]+Coverage for:", re.MULTILINE)
_COLUMN_GAP = re.compile(r" {2,}")
_PAGE_FOOTER = re.compile(r"^(?:Page \d+ of \d+|\d+ of \d+)$")
# A left cell narrower than this is a table's padding column, not its labels.
_PADDING_WIDTH = 12

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
_CHART_END = ("Excluded Services", "Services Your Plan", "Other Covered Services",
              "About these Coverage Examples", "This is not a cost estimator")
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


def read_pdf(path: Path) -> list[PdfPage]:
    try:
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise SbcParseError(f"{len(pdf.pages)} pages, more than an SBC has")
            # dedupe_chars: some issuers print a second, offset text layer.
            return [_read_page(page.dedupe_chars()) for page in pdf.pages]
    except SbcParseError:
        raise
    except Exception as exc:
        raise SbcParseError(f"unreadable PDF ({type(exc).__name__})") from exc


def _read_page(page) -> PdfPage:
    return PdfPage(text=_band(page, page.bbox), rows=tuple(_table_rows(page)),
                   examples=tuple(_example_columns(page)))


def _band(page, bbox, layout: bool = True) -> str:
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

    text = page.filter(inside).extract_text(layout=layout) or ""
    lines = (_COLUMN_GAP.sub(" | ", line.strip()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _table_rows(page) -> list[TableRow]:
    """Each left-column cell of each table, with the rest of its row, top to bottom.

    A merged left cell spans every row of its group, so its band carries the
    whole group. pdfplumber can find a table again inside a larger one, so
    larger tables are read first and a cell inside one already read is skipped.
    """
    taken: list[tuple[float, float]] = []
    rows = []
    tables = sorted(page.find_tables(), key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]), reverse=True)
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
            label = " ".join(_band(page, (x0, top, edge, bottom), layout=False).split())
            rows.append((top, TableRow(label, _band(page, (edge, top, x1, bottom)))))
    return [row for _, row in sorted(rows, key=lambda r: r[0])]


def _label_edge(left_cells) -> float | None:
    """Where the table's label column ends: the right edge most of its real left cells share.

    Some issuers draw a thin padding column at the left of a row; that cell is
    not the label, and the label printed beside it belongs to this column.
    """
    edges = Counter(round(c[2]) for c in left_cells if c[2] - c[0] >= _PADDING_WIDTH)
    return edges.most_common(1)[0][0] if edges else None


def _example_columns(page) -> list[str]:
    """The three coverage examples, cut apart at each column's left edge.

    Titles are centred, so they don't mark where a column starts; the
    template's left-aligned "This EXAMPLE event includes" line does, once
    per column.
    """
    titles = [page.search(title) for title, _ in COVERAGE_EXAMPLES]
    anchors = sorted(hit["x0"] for hit in page.search(_EXAMPLE_ANCHOR))
    if not all(titles) or len(anchors) != len(COVERAGE_EXAMPLES):
        return []
    top = min(hits[0]["top"] for hits in titles)
    edges = [page.bbox[0], *(x - 1 for x in anchors[1:]), page.bbox[2]]
    return [_band(page, (left, top, right, page.bbox[3]), layout=False) for left, right in pairwise(edges)]


def parse_sbc(pages: list[PdfPage]) -> SbcParse:
    """The template's sections, in reading order. Raises SbcParseError if it has none of them."""
    if not pages:
        raise SbcParseError("no pages")
    first = pages[0].text
    year = _COVERAGE_PERIOD.search(first)
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
        if row.label.startswith(_QUESTIONS_HEADER):
            active = True
            continue
        if row.label.startswith(_CHART_HEADER):
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
    that doesn't open a group continues the one before it.
    """
    sections: list[Section] = []
    active = False
    for row in rows:
        if row.label.startswith(_CHART_HEADER):
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
