"""The committed source registry: what PolicyPal reads, and whether it may (ADR 0025)."""
import pytest

from src.ingestion.sources import ALL_SOURCES, SOURCES, enabled_sources
from src.ingestion.sources.base import Source
from src.ingestion.sources.registry import (
    APPROVED,
    RegistryError,
    SourceNotApprovedError,
    load_registry,
    require_enabled,
    sbc_host_for,
)

_ENTRY = """
[[source]]
id = "{id}"
name = "A source"
publisher = "Someone"
scope_urls = ["https://example.com/"]
kind = "corpus"
jurisdiction = "US"
license = "Public domain"
license_url = "https://example.com/license"
permission_status = "{permission}"
commercial_use = "yes"
robots = "allowed"
robots_checked_on = 2026-09-24
access = "crawl"
verified_on = 2026-09-24
enabled = {enabled}
removal = "Disable it."
notes = ""
"""


def _entry(id_="x", permission="denied", enabled="false"):
    return _ENTRY.format(id=id_, permission=permission, enabled=enabled)


def _write(tmp_path, text):
    path = tmp_path / "registry.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_committed_registry_is_valid_and_complete():
    registry = load_registry()

    assert {"wikipedia", "healthcare_gov", "cms_marketplace_api", "cms_ca_sbe_puf",
            "cms_ca_rating_areas", "coveredca"} <= set(registry)
    # Every enabled source carries a permission that allows it, and says how to take it out.
    for entry in registry.values():
        assert not entry.enabled or entry.permission_status in APPROVED
        assert entry.removal.strip()


def test_every_corpus_source_in_the_code_is_registered_and_the_enabled_ones_run():
    registry = load_registry()

    assert all(source.registry_id in registry for source in ALL_SOURCES)
    assert [s.registry_id for s in SOURCES] == ["wikipedia", "healthcare_gov"]


def test_covered_california_is_recorded_as_link_only_and_refused():
    coveredca = load_registry()["coveredca"]

    assert (coveredca.enabled, coveredca.permission_status, coveredca.access) == (False, "denied", "link")
    assert "automated" in coveredca.notes
    with pytest.raises(SourceNotApprovedError, match="disabled"):
        require_enabled("coveredca")


def test_the_california_catalog_source_is_approved():
    assert require_enabled("cms_ca_sbe_puf").permission_status == "public_domain"


def test_an_unregistered_source_is_refused():
    with pytest.raises(SourceNotApprovedError, match="not in the source registry"):
        require_enabled("no_such_source")


def test_only_an_approved_permission_can_be_enabled(tmp_path):
    for permission in ("pending_review", "denied"):
        with pytest.raises(RegistryError, match="x: enabled needs permission_status"):
            load_registry(_write(tmp_path, _entry(permission=permission, enabled="true")))
    assert load_registry(_write(tmp_path, _entry(permission="written_permission", enabled="true")))["x"].enabled


def test_a_missing_field_or_unknown_value_is_named(tmp_path):
    with pytest.raises(RegistryError, match="x: missing removal"):
        load_registry(_write(tmp_path, _entry().replace('removal = "Disable it."\n', "")))
    with pytest.raises(RegistryError, match="x: kind 'website'"):
        load_registry(_write(tmp_path, _entry().replace('kind = "corpus"', 'kind = "website"')))
    with pytest.raises(RegistryError, match="x: unknown field licence"):
        load_registry(_write(tmp_path, _entry() + 'licence = "typo"\n'))
    with pytest.raises(RegistryError, match="x: jurisdiction"):
        load_registry(_write(tmp_path, _entry().replace('jurisdiction = "US"', 'jurisdiction = "California"')))
    with pytest.raises(RegistryError, match="x: enabled must be"):
        load_registry(_write(tmp_path, _entry(enabled='"yes"')))


def test_robots_must_have_been_checked_unless_it_does_not_apply(tmp_path):
    unchecked = _entry().replace("robots_checked_on = 2026-09-24\n", "")
    with pytest.raises(RegistryError, match="x: robots_checked_on"):
        load_registry(_write(tmp_path, unchecked))

    not_applicable = unchecked.replace('robots = "allowed"', 'robots = "not_applicable"')
    assert load_registry(_write(tmp_path, not_applicable))["x"].robots_checked_on is None


def test_duplicate_ids_and_broken_toml_are_refused(tmp_path):
    with pytest.raises(RegistryError, match="duplicate id 'x'"):
        load_registry(_write(tmp_path, _entry() + _entry()))
    with pytest.raises(RegistryError, match="not valid TOML"):
        load_registry(_write(tmp_path, "[[source]\nid = "))


def test_a_disabled_source_is_left_out_of_the_run():
    class _Denied(Source):
        name = registry_id = "coveredca"

        def fetch(self): ...

        def normalize(self): ...

        def chunk_documents(self):
            return []

    class _Unregistered(_Denied):
        name = registry_id = "nobody_approved_this"

    assert enabled_sources([_Denied(), _Unregistered()]) == []


def _sbc_host(id_="h", prefix="https://sbc.example.com/", commercial="review", enabled="true", kind="sbc_host"):
    return (_entry(id_, "mandated_disclosure", enabled)
            .replace('kind = "corpus"', f'kind = "{kind}"')
            .replace('commercial_use = "yes"', f'commercial_use = "{commercial}"')
            .replace('scope_urls = ["https://example.com/"]', f'scope_urls = ["{prefix}"]'))


def test_a_mandated_disclosure_is_approved_only_for_an_sbc_host_under_review(tmp_path):
    """An SBC is published because the law requires it; that is not a licence (ADR 0026)."""
    assert load_registry(_write(tmp_path, _sbc_host()))["h"].enabled

    for broken in (_sbc_host(kind="corpus"), _sbc_host(commercial="yes"), _sbc_host(commercial="no")):
        with pytest.raises(RegistryError, match="h: mandated_disclosure is only for an sbc_host"):
            load_registry(_write(tmp_path, broken))


def test_the_sbc_host_is_the_longest_prefix_covering_the_link_enabled_or_not(tmp_path, monkeypatch):
    from src.ingestion.sources import registry

    loaded = load_registry(_write(tmp_path, "".join([
        _sbc_host("broad", "https://sbc.example.com/"),
        _sbc_host("narrow", "https://sbc.example.com/ca/", enabled="false"),
        _entry("corpus").replace('scope_urls = ["https://example.com/"]', 'scope_urls = ["https://corpus.example.com/"]'),
    ])))
    monkeypatch.setattr(registry, "_committed", lambda: loaded)

    assert sbc_host_for("https://sbc.example.com/ca/gold.pdf").id == "narrow"
    assert sbc_host_for("https://sbc.example.com/tx/gold.pdf").id == "broad"
    assert sbc_host_for("https://corpus.example.com/gold.pdf") is None   # not an sbc_host
    assert sbc_host_for("https://sbc.example.com.evil.test/gold.pdf") is None


def test_every_california_carrier_is_a_mandated_disclosure_under_review():
    hosts = {id_: e for id_, e in load_registry().items() if e.kind == "sbc_host" and e.jurisdiction == "CA"}

    assert len(hosts) == 11
    for entry in hosts.values():
        assert (entry.permission_status, entry.commercial_use) == ("mandated_disclosure", "review")
        assert all(prefix.startswith("https://") for prefix in entry.scope_urls)


def test_carriers_whose_terms_ban_robots_are_never_crawled():
    """The user's rule (ADR 0026): website Terms govern, as for Covered California."""
    registry = load_registry()

    for id_ in ("sbc_kaiser_ca", "sbc_blue_shield_ca", "sbc_western_health_advantage", "sbc_anthem_ca",
                "sbc_la_care", "sbc_valley_health_plan"):
        assert registry[id_].access == "manual", id_
    assert not registry["sbc_health_net_ca"].enabled


@pytest.mark.parametrize("scope", ['"https://sbc.example.com/"', '["https://sbc.example.com"]',
                                   '["http://sbc.example.com/"]', '["sbc.example.com/"]', '[42]'])
def test_a_scope_must_be_https_with_a_path_after_the_host(tmp_path, scope):
    """Links are matched by prefix: without the "/", https://sbc.example.com would also match
    https://sbc.example.com.evil.test/…"""
    with pytest.raises(RegistryError, match="x: scope_urls .* must be a list of https://host/"):
        load_registry(_write(tmp_path, _entry().replace('["https://example.com/"]', scope)))
