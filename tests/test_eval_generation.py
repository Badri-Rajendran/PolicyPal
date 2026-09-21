"""The coverage scorer, on canned answers: no model, no database (ADR 0017).

A scorer that passes a wrong answer hides exactly the failure its eval set
exists to catch, so it is tested like any other code.
"""
from scripts.eval_generation import (
    CoverageCase,
    Missing,
    corpus_citations,
    score_coverage,
)
from src.services.generation import NO_ANSWER_RESPONSE, ShownPlan

_READ = ShownPlan(1, "11111FL0010001", "Gold 1000", "Example", "Gold", 2026)
_BLOCKED = ShownPlan(2, "22222TX0010001", "Silver Classic", "Example", "Silver", 2026)
_PDF = "https://sbc.example.com/2026_22222TX001000101.pdf"
_GAP = Missing(_BLOCKED, "blocked", "Silver Classic")
_STATUSES = {_BLOCKED.plan_id: "blocked"}
_READ_CITE = "[Source: Gold 1000 - Summary of Benefits - If you have a test.pdf]"

_ONLY_MISSING = CoverageCase("Does the second plan cover MRIs?", (_READ, _BLOCKED), (_PDF,), missing=(_GAP,))
_MIXED = CoverageCase("Compare their MRI costs.", (_READ, _BLOCKED), (_PDF,), (_READ,), missing=(_GAP,))


def _score(case, text, cited=frozenset(), statuses=None):
    problem = score_coverage(case, text, set(cited), _STATUSES if statuses is None else statuses)
    return problem and problem[0]


def test_naming_the_unreadable_plan_and_linking_its_pdf_passes():
    assert _score(_ONLY_MISSING, f"Silver Classic's Summary of Benefits couldn't be read here: {_PDF}") is None


def test_an_unreadable_plan_described_from_general_material_fails():
    text = (f"Silver Classic's document couldn't be read here ({_PDF}), but plans generally cover MRIs. "
            "[Source: hcg_glossary_diagnostic_test.md]")

    assert _score(_ONLY_MISSING, text) == "CORPUS"


def test_leaving_the_unreadable_plan_unnamed_fails():
    assert _score(_ONLY_MISSING, f"That plan's document couldn't be read here: {_PDF}") == "SILENT"


def test_a_figure_for_a_plan_with_no_document_is_fabricated():
    text = f"Silver Classic's document couldn't be read here ({_PDF}); an MRI there is usually 20%."

    assert _score(_ONLY_MISSING, text) == "FABRICATED"


def test_figures_inside_the_linked_pdf_address_are_not_fabricated():
    pdf = "https://sbc.example.com/2026/$0_Silver_100%25.pdf"
    case = CoverageCase("Does the second plan cover MRIs?", (_READ, _BLOCKED), (pdf,), missing=(_GAP,))

    assert _score(case, f"Silver Classic's document couldn't be read here: {pdf}") is None


def test_a_figure_in_the_plans_own_name_is_not_fabricated():
    plan = ShownPlan(1, "33333NC0010001", "Silver Preferred | $10 Tier 1 Rx", "Example", "Silver", 2026)
    case = CoverageCase("Does it cover MRIs?", (plan,), (_PDF,), missing=(Missing(plan, "blocked", "Silver Preferred"),))

    assert _score(case, f"Silver Preferred | $10 Tier 1 Rx couldn't be read here: {_PDF}",
                  statuses={plan.plan_id: "blocked"}) is None


def test_general_rules_added_for_an_unreadable_plan_are_caught_even_uncited():
    text = (f"Silver Classic's document couldn't be read here: {_PDF}. Generally, Marketplace plans cover "
            "preventive care at $0 in network.")

    assert _score(_ONLY_MISSING, text) == "FABRICATED"


def test_a_comparison_must_cite_the_readable_plan_and_name_the_other():
    named = f"Gold 1000: $100 per MRI {_READ_CITE}. Silver Classic's couldn't be read here: {_PDF}"
    skipped = f"Gold 1000: $100 per MRI {_READ_CITE}. See {_PDF} for the other."

    assert _score(_MIXED, named, {"Gold 1000"}) is None
    assert _score(_MIXED, skipped, {"Gold 1000"}) == "SILENT"
    assert _score(_MIXED, named, set()) == "WRONG CITE"


def test_a_definitional_answer_may_cite_general_material():
    case = CoverageCase("What is coinsurance?", (_READ,), ("coinsurance",), corpus_ok=True)

    assert _score(case, "Coinsurance is your share. [Source: hcg_glossary_coinsurance.md]") is None


def test_a_plan_that_has_since_been_read_fails_as_a_fixture_not_as_a_pass():
    text = f"Silver Classic's document couldn't be read here: {_PDF}"

    assert _score(_ONLY_MISSING, text, statuses={_BLOCKED.plan_id: "ok"}) == "FIXTURE"


def test_declining_a_question_about_an_unreadable_plan_is_a_miss():
    assert _score(_ONLY_MISSING, NO_ANSWER_RESPONSE) == "NO ANSWER"


def test_citations_are_read_from_brackets_and_sbc_labels_are_not_general_material():
    text = ("Coinsurance [Source: hcg_glossary_coinsurance.md; Health_insurance] and "
            f"{_READ_CITE}. The word Deductible alone is not a citation.")

    assert corpus_citations(text) == ["Health_insurance", "hcg_glossary_coinsurance.md"]


def test_citing_the_unreadable_plans_own_pdf_is_not_general_material():
    text = f"Silver Classic's document couldn't be read here. [Source: {_PDF}]"

    assert corpus_citations(text) == []
    assert _score(_ONLY_MISSING, text) is None


def test_naming_an_unreadable_plan_in_a_citation_is_not_citing_general_material():
    """The model writes "[Source: Silver Classic — reason: …]": that names a plan, not a document."""
    text = "[Source: Silver Classic — reason: the insurer's website doesn't allow automated downloads]"

    assert corpus_citations(text) == ["Silver Classic — reason: the insurer's website doesn't allow automated downloads"]
    assert corpus_citations(text, ("Silver Classic",)) == []
