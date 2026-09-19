"""Reading an SBC into the federal template's sections (ADR 0013).

The pages here are hand-written in the shape `read_pdf` returns, modelled on
real layouts: wrapped questions, a heading cut by a page break, an answer
printed above its question. No issuer PDF is committed — the repository is
public — so real documents are checked by the live ingest instead.
"""
from itertools import pairwise

import pytest

from src.ingestion.sbc.extract import (
    PdfPage,
    SbcParseError,
    TableRow,
    _group_lines,
    parse_sbc,
    read_pdf,
)

HEADER = (
    "Summary of Benefits and Coverage: What this Plan Covers & What You Pay for Covered Services "
    "Coverage Period: 01/01/2026-12/31/2026\n"
    ": Example Gold HMO | Coverage for: Individual + Family | Plan Type: HMO"
)


def _page(text=HEADER, rows=(), examples=()):
    return PdfPage(text=text, rows=tuple(TableRow(label, body) for label, body in rows), examples=examples)


def _sections(*pages):
    return {s.heading: s.text for s in parse_sbc(list(pages)).sections}


def test_title_and_coverage_year_come_from_the_first_page():
    parse = parse_sbc([_page(rows=[("Common Medical Event", ""), ("If you have a test", "x")])])

    assert (parse.title, parse.coverage_year) == ("Example Gold HMO", 2026)


def test_a_wrapped_question_collects_its_answer_even_when_printed_above_it():
    sections = _sections(_page(rows=[
        ("Some introduction", "not part of any question"),
        ("Important Questions", "Answers | Why This Matters:"),
        ("What is the overall deductible?", "$1,500 | Generally, you must pay..."),
        ("", "| This plan covers some items before the deductible."),
        ("Are there services", "Yes. Preventive care"),
        ("covered before you meet", ""),
        ("your deductible?", "is covered first."),
        ("Common Medical Event", "Services You May Need"),
    ]))

    assert sections["What is the overall deductible?"] == "$1,500 | Generally, you must pay..."
    assert sections["Are there services covered before you meet your deductible?"] == (
        "| This plan covers some items before the deductible.\nYes. Preventive care\nis covered first."
    )
    assert "Some introduction" not in " ".join(sections)


def test_headings_worded_or_wrapped_differently_are_filed_under_the_templates():
    sections = _sections(_page(rows=[
        ("Important Questions", "Answers"),
        ("What is the out-of- pocket limit for this plan?", "$9,900"),
        ("What is not included in theout–of–pocket limit?", "Premiums"),
        ("Do I need a referral to see aspecialist?", "No."),
        ("Common Medical Event", "What You Will Pay"),
        ("If you have mental health, behavioral health, or substance abuse services", "Outpatient $70"),
        ("If you have a pet", "Not a template heading"),
    ]))

    assert sections["What is the out-of-pocket limit for this plan?"] == "$9,900"
    assert sections["What is not included in the out-of-pocket limit?"] == "Premiums"
    assert sections["Do you need a referral to see a specialist?"] == "No."
    assert sections["If you need mental health, behavioral health, or substance abuse services"] == "Outpatient $70"
    assert sections["If you have a pet"] == "Not a template heading"


IMAGING_ROWS = "Imaging (CT/PET scans, | Preauthorization is required.\n$400 copayment/visit Not covered\nMRIs)"
RX_NOTE = "More information about prescription drug coverage is available at https://example.com/rx"


def test_a_chart_group_keeps_every_row_and_moves_a_label_note_into_its_text():
    sections = _sections(_page(rows=[
        ("Common Medical Event", "What You Will Pay"),
        ("If you have a test", IMAGING_ROWS),
        (f"If you need drugs to treat your illness or condition {RX_NOTE}", "Generic drugs $5 copay"),
    ]))

    assert "$400 copayment/visit" in sections["If you have a test"]
    drugs = sections["If you need drugs to treat your illness or condition"]
    assert drugs.startswith("More information about prescription drug coverage")
    assert drugs.endswith("Generic drugs $5 copay")


def test_a_group_cut_by_a_page_break_is_rejoined_under_its_full_heading():
    """The heading starts in one page's row text and ends as the next page's label."""
    sections = _sections(
        _page(rows=[
            ("Common Medical Event", "What You Will Pay"),
            ("If you have a test", "Diagnostic test $60"),
            ("", "If you need drugs to | Tier 1 - Generic $3"),
        ]),
        _page(text="", rows=[
            ("Common Medical Event", "What You Will Pay"),
            ("condition More information about prescription drug coverage", "Tier 2 - Brand $60"),
            ("", "Specialty drugs 50% coinsurance"),
            ("If you have outpatient surgery", "Facility fee 40%"),
        ]),
    )

    drugs = sections["If you need drugs to treat your illness or condition"]
    assert "Tier 1 - Generic $3" in drugs and "Tier 2 - Brand $60" in drugs and "Specialty drugs" in drugs
    assert sections["If you have outpatient surgery"] == "Facility fee 40%"
    assert "Tier 2" not in sections["If you have a test"]


def test_a_label_split_across_two_cells_is_joined_into_its_heading():
    """Too short to tell apart alone: "If you have a" begins two headings."""
    sections = _sections(_page(rows=[
        ("Common Medical Event", "What You Will Pay"),
        ("If you have a", "Facility fee (e.g., hospital room) $350 copay per day"),
        ("hospital stay", "Physician/surgeon fees No charge"),
        ("If you are pregnant", "Office visits No charge"),
    ]))

    assert sections["If you have a hospital stay"] == (
        "Facility fee (e.g., hospital room) $350 copay per day\nPhysician/surgeon fees No charge"
    )
    assert "If you have a" not in sections


def test_the_chart_ends_at_the_next_template_heading():
    sections = _sections(_page(rows=[
        ("Common Medical Event", "What You Will Pay"),
        ("If your child needs dental or eye care", "Children's eye exam No charge"),
        ("Services Your Plan Generally Does NOT Cover", "• Acupuncture"),
        ("", "Peg is Having a Baby"),
    ]))

    assert sections["If your child needs dental or eye care"] == "Children's eye exam No charge"


def test_text_sections_are_cut_at_the_template_headings():
    text = (
        f"{HEADER}\nExcluded Services & Other Covered Services:\n"
        "Services Your Plan Generally Does NOT Cover (Check your policy.)\n"
        "• | Acupuncture | • Cosmetic surgery\nPage 5 of 7\n"
        "Other Covered Services (Limitations may apply.)\n• Chiropractic care\n"
        "Your Rights to Continue Coverage: call the state.\n"
        "Your Grievance and Appeals Rights: you can appeal.\n"
        "Does this plan provide Minimum Essential Coverage? Yes\n"
        "To see examples of how this plan might cover costs, see the next section.\n"
        "About these Coverage Examples: Peg is Having a Baby"
    )
    sections = _sections(_page(text=text))

    assert sections["Services your plan does not cover"] == "(Check your policy.)\n• Acupuncture | • Cosmetic surgery"
    assert sections["Other covered services"] == "(Limitations may apply.)\n• Chiropractic care"
    assert sections["Grievance and appeals rights"] == "you can appeal."
    assert sections["Minimum essential coverage and value"] == "Coverage? Yes"


def test_coverage_examples_are_filed_by_name_and_end_at_their_total():
    sections = _sections(_page(examples=(
        "Peg is Having a Baby\nTotal Example Cost $12,700\nThe total Peg would pay is $2,660\nThe plan would be",
        "Managing Joe's Type 2 Diabetes\nThe total Joe would pay is $1,000",
        "Mia's Simple Fracture\nThe total Mia would pay is $1,400\nPage 7 of 7",
    )))

    assert sections["Coverage example: Peg is having a baby"].endswith("The total Peg would pay is $2,660")
    assert sections["Coverage example: Mia's simple fracture"].endswith("$1,400")
    assert "Coverage example: Managing Joe's type 2 diabetes" in sections


def test_a_file_with_none_of_the_template_is_refused():
    with pytest.raises(SbcParseError, match="none of the template"):
        parse_sbc([_page(text="An unrelated brochure")])


def test_a_file_that_is_not_a_pdf_is_refused_without_quoting_it(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"<html>secret-looking content</html>")

    with pytest.raises(SbcParseError) as raised:
        read_pdf(path)
    assert "secret" not in str(raised.value)


# The ruled grid (ADR 0018). Cells are pdfplumber's (x0, top, x1, bottom); the
# text is words placed at points, read back by whichever box holds them.

def _reader(words):
    def read(box, layout):
        x0, top, x1, bottom = box
        inside = sorted((y, x, text) for x, y, text in words if x0 <= x <= x1 and top <= y <= bottom)
        lines = {}
        for y, _, text in inside:
            lines.setdefault(y, []).append(text)
        return "\n".join(" ".join(line) for line in lines.values())
    return read


def _grid(columns, rows):
    """A plain grid: each column's edges and each row's edges."""
    return [(a, top, b, bottom) for top, bottom in pairwise(rows) for a, b in pairwise(columns)]


def test_a_wrapped_service_name_is_written_on_one_line_with_its_costs():
    """CHRISTUS's imaging row: the name wraps around its price, which sat on a line of its own."""
    cells = _grid([0, 100, 200, 300, 400], [0, 30, 60])
    words = [(5, 10, "Diagnostic test"), (150, 10, "$80 copay"), (250, 10, "Not covered"), (350, 10, "None"),
             (5, 35, "Imaging (CT/PET"), (150, 45, "No charge"), (250, 45, "Not covered"),
             (350, 45, "Preauthorization is required."), (5, 55, "scans, MRIs)")]

    assert _group_lines(cells, (0, 0, 400, 60), _reader(words)) == (
        "Diagnostic test | $80 copay | Not covered | None\n"
        "Imaging (CT/PET scans, MRIs) | No charge | Not covered | Preauthorization is required."
    )


def test_a_cell_merged_across_rows_or_a_box_inside_a_cell_does_not_cut_a_row():
    """Baylor merges "None" across two services; CHRISTUS boxes a phrase inside a cell."""
    cells = [
        (0, 0, 100, 30), (100, 0, 200, 30),
        (0, 30, 100, 60), (100, 30, 200, 60),
        (200, 0, 300, 60),      # a limitation shared by both rows
        (10, 40, 60, 50),       # a box inside the second service's cell
    ]
    words = [(5, 10, "Emergency transport"), (150, 10, "50%"), (250, 30, "None"),
             (5, 45, "Urgent care"), (150, 45, "$75")]

    lines = _group_lines(cells, (0, 0, 300, 60), _reader(words)).splitlines()

    assert len(lines) == 2
    assert lines[0].startswith("Emergency transport | 50%")
    assert lines[1].startswith("Urgent care | $75")


def test_a_padding_cell_beside_the_service_still_starts_a_row():
    """The service cell can sit inside a thin padding column, which the rule crosses too."""
    cells = [(0, 0, 100, 30), (100, 0, 200, 30), (200, 0, 300, 30),
             (0, 30, 5, 60), (5, 30, 95, 60), (95, 30, 100, 60), (100, 30, 200, 60), (200, 30, 300, 60)]
    words = [(20, 10, "Emergency room care"), (150, 10, "$950"), (250, 10, "$950"),
             (20, 45, "Urgent care"), (150, 45, "$80"), (250, 45, "Not covered")]

    assert _group_lines(cells, (0, 0, 300, 60), _reader(words)).splitlines() == [
        "Emergency room care | $950 | $950", "Urgent care | $80 | Not covered",
    ]


def test_a_group_without_column_rules_keeps_its_layout_text():
    words = [(5, 10, "Primary care visit"), (150, 10, "$20 copay")]

    assert _group_lines([], (0, 0, 300, 30), _reader(words)) == "Primary care visit $20 copay"


def test_a_pdf_with_no_text_layer_is_refused_as_a_scanned_image(tmp_path):
    """No OCR (ADR 0018): an image-only SBC is recorded as unparseable, with the reason."""
    import pypdfium2

    pdf = pypdfium2.PdfDocument.new()
    pdf.new_page(612, 792)
    pdf.save(tmp_path / "scanned.pdf")

    with pytest.raises(SbcParseError, match="no text layer"):
        read_pdf(tmp_path / "scanned.pdf")
