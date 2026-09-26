"""The passages service: brief quotes of cited passages, with their source (ADR 0027)."""
from src.ingestion.sources.registry import registered
from src.models.chunk import Chunk
from src.models.sbc import SbcChunk, SbcDocument
from src.policypal.config import settings
from src.services.passages import EXCERPT_CHARS, content_hash, excerpt, passage_for

LONG = ("Emergency room care | $400 copay/visit; deductible does not apply | Cost sharing waived if admitted.\n"
        "Emergency medical transportation | $250 copay/trip; deductible does not apply | None\n"
        "Urgent care | $50 copay/visit; deductible does not apply | $50 copay/visit; deductible does not apply\n"
        "Hospital stay | 30% coinsurance | Preauthorization is required for non-emergency services.")


def test_a_short_passage_is_returned_whole():
    assert excerpt("Copayment: A fixed amount you pay.", "anything") == "Copayment: A fixed amount you pay."


def test_a_passage_of_exactly_the_limit_is_returned_whole():
    text = "x" * EXCERPT_CHARS
    assert excerpt(text, "anything") == text


def test_the_excerpt_starts_at_the_segment_most_like_the_answer():
    text = excerpt(LONG, "It charges a $50 copay per urgent care visit.")
    assert text.startswith("… Urgent care | $50 copay/visit")
    assert text.endswith("non-emergency services.")          # reaches the end: no trailing mark
    assert len(text.removeprefix("… ").removesuffix(" …")) <= EXCERPT_CHARS


def test_sentences_within_a_line_are_segments():
    passage = "A plan pays its share. " * 15 + "Coinsurance is your share of the costs after the deductible."
    assert excerpt(passage, "coinsurance share costs").startswith("… Coinsurance is your share")


def test_ties_go_to_the_earlier_segment():
    assert excerpt(LONG, "nothing in common here").startswith("Emergency room care")


def test_a_cut_excerpt_is_marked_at_the_end():
    text = excerpt(LONG, "Emergency room care")
    assert text.startswith("Emergency room care") and text.endswith(" …")
    assert len(text.removesuffix(" …")) <= EXCERPT_CHARS


def test_a_single_long_segment_is_cut_at_a_space():
    words = " ".join(["deductible"] * 60)
    text = excerpt(words, "deductible")
    body = text.removesuffix(" …")
    assert len(body) <= EXCERPT_CHARS and not body.endswith(" ") and text.endswith(" …")
    assert body.split(" ")[-1] == "deductible"                # no word cut in half


def test_empty_inputs():
    assert excerpt("", "x") == ""
    assert excerpt(LONG, "").startswith("Emergency room care")


def test_content_hash_is_the_sha256_hex_digest():
    assert content_hash("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_registered_returns_an_entry_or_none():
    assert registered("wikipedia").license == "CC BY-SA 4.0"
    assert registered("no-such-source") is None


def _sbc(session, url="https://www.sharphealthplan.com/docs/sbc.pdf"):
    doc = SbcDocument(url=url, plan_year=2026, status="ok", title="Sharp Health Plan: Sharp Silver 70 Premier HMO")
    session.add(doc)
    session.flush()
    session.add(SbcChunk(document_id=doc.id, chunk_id="sbc_2026_abc_s11_c00",
                         section="If you need immediate medical attention", position=0, content=LONG))
    session.flush()


SBC_LABEL = "Sharp Silver 70 Premier HMO - Summary of Benefits - If you need immediate medical attention.pdf"


def test_an_sbc_passage(session):
    _sbc(session)
    p = passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, content_hash(LONG), "urgent care $50")
    assert (p.kind, p.title, p.document, p.section, p.status) == (
        "sbc", "Sharp Silver 70 Premier HMO", "Summary of Benefits and Coverage, 2026",
        "If you need immediate medical attention", "ok")
    assert p.url == "https://www.sharphealthplan.com/docs/sbc.pdf" and p.license is None
    assert p.quote.startswith("… Urgent care")


def test_a_plan_name_with_a_dot_keeps_it(session):
    p = passage_for(session, "sbc_2026_gone_s01_c00", "Silver 2.0 HMO - Summary of Benefits - Costs.pdf", None, "")
    assert (p.title, p.section) == ("Silver 2.0 HMO", "Costs")


def test_an_unsafe_document_url_is_dropped(session):
    _sbc(session, url="http://www.sharphealthplan.com/docs/sbc.pdf")
    assert passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, None, "").url is None


def test_a_document_url_on_an_ip_address_is_dropped(session):
    _sbc(session, url="https://10.0.0.1/docs/sbc.pdf")
    assert passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, None, "").url is None


def test_statuses(session):
    _sbc(session)
    unverified = passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, None, "")
    assert unverified.status == "unverified" and unverified.quote
    changed = passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, content_hash("other text"), "")
    assert (changed.status, changed.quote) == ("changed", None)
    missing = passage_for(session, "sbc_2026_gone_s01_c00", SBC_LABEL, None, "")
    assert (missing.status, missing.quote, missing.title) == ("missing", None, "Sharp Silver 70 Premier HMO")
    assert (missing.document, missing.url) == ("Summary of Benefits and Coverage, 2026", None)


def _chunk(session, chunk_id, source, content):
    session.add(Chunk(chunk_id=chunk_id, source=source, content=content, embedding=[0.0] * settings.embedding_dim))
    session.flush()


def test_a_wikipedia_passage_is_credited_from_the_registry(session):
    _chunk(session, "wikipedia_Test_passage_s0_c00", "wiki_Health_insurance.txt",
           "Health insurance covers medical expenses.")
    p = passage_for(session, "wikipedia_Test_passage_s0_c00", "wiki_Health_insurance.txt",
                    content_hash("Health insurance covers medical expenses."), "")
    assert (p.kind, p.title, p.document, p.section, p.status) == (
        "wikipedia", "Health insurance", "Wikipedia article", None, "ok")
    assert p.quote == "Health insurance covers medical expenses."
    assert p.url == "https://en.wikipedia.org/wiki/Health_insurance"
    assert p.license == {"name": "CC BY-SA 4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/"}


def test_a_wikipedia_url_is_quoted(session):
    p = passage_for(session, "wikipedia_x_s0_c00", "wiki_Title_insurance?x=1.txt", None, "")
    assert p.url == "https://en.wikipedia.org/wiki/Title_insurance%3Fx%3D1"


def test_a_healthcare_gov_passage(session):
    _chunk(session, "healthcare_gov_glossary_Test_passage_s0_c00", "hcg_glossary_Copayment.md",
           "Copayment: A fixed amount you pay for a plan-covered service, like $30.")
    p = passage_for(session, "healthcare_gov_glossary_Test_passage_s0_c00", "hcg_glossary_Copayment.md", None, "")
    assert (p.kind, p.title, p.document, p.url, p.license, p.status) == (
        "healthcare_gov", "Copayment", "HealthCare.gov glossary", None, None, "unverified")


def test_a_healthcare_gov_article(session):
    p = passage_for(session, "healthcare_gov_article_x_s0_c00", "hcg_article_Using_your_plan.md", None, "")
    assert (p.kind, p.title, p.document) == ("healthcare_gov", "Using your plan", "HealthCare.gov article")


def test_any_other_label(session):
    p = passage_for(session, "other_s0_c00", "notes.md", None, "")
    assert (p.kind, p.title, p.document, p.url, p.license, p.status) == ("other", "notes", None, None, None, "missing")
