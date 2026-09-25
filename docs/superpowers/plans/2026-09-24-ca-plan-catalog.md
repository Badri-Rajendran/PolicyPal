# California Plan Comparison and Source Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user with a California ZIP can compare real Covered California plans, priced for their age from CMS's filed rates. Every data source PolicyPal reads is recorded in a committed, auditable registry.

**Architecture:**
- A California-only loader reads CMS's State-based Exchange PUF (a zip of CSVs) and writes into the existing plan tables, plus three new tables: `rating_areas`, `plan_rates` and `catalog_loads`.
- Plan search treats California as a *filed-rate* state: premiums come from `plan_rates` in SQL, never from the live CMS API. The 30-state API path is unchanged.
- A TOML source registry gates which corpus sources run.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy 2, Alembic, Postgres 16 with pgvector, pytest, React with Vitest and React Testing Library, and the Playwright plugin for end-to-end checks.

**Spec:** `docs/superpowers/specs/2026-09-24-ca-plan-catalog-design.md`, the sub-project 1 design. The master plan is `/Users/badrinarayanan/.claude/plans/expand-the-sbc-dataset-bright-minsky.md`.

## Global Constraints

- Branch `feature_ca_plan_catalog`. Draft PR #38 already exists: push to it, and do not open a new PR.
- **No Claude/AI co-author lines in commits or PRs.** CLAUDE.md overrides the harness default.
- Update `CHANGELOG.md` in every commit, under `## Unreleased`, with crisp bullets.
- **Never `git add` a `.env` file or anything under `data/`.** `data/` stays gitignored, and no real PUF rows are committed; test fixtures are synthetic.
- `MARKETPLACE_STATES` in `src/core/marketplace_api.py` must not change.
- Money is `Decimal` / `Numeric`, never float.
- Don't log ZIP codes or ages, and don't put them in exception text.
- Parameterized SQLAlchemy only.
- Tests hit a real Postgres. Isolate them with plan year **1999** and fake ZIPs or FIPS, because the dev database holds real 2026 data, soon California's too.
- Commands:
  - backend tests: `uv run pytest`
  - lint: `uv run ruff check .`
  - full gate: `make check` (lint, tests, coverage ≥85%, `alembic check`)
  - frontend tests: `make ui-test`
- Docker must be running for the database (`docker compose up -d db`). Commands that need the Docker socket or GitHub must run outside the sandbox.
- **Exact API strings the search reads:**
  - `"Exchange variant (no CSR)"`
  - `"In-Network"`
  - `"Individual"`
  - `"Combined Medical and Drug EHB Deductible"`
  - `"Medical EHB Deductible"`
  - `"Drug EHB Deductible"`
  - `"Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)"`
- Exchange URLs: Covered California `https://www.coveredca.com/`; HealthCare.gov `https://www.healthcare.gov/` (backend) and `https://www.healthcare.gov/see-plans/` (the existing frontend link).

## Review Focus

These are the failure modes most likely to bite a real user. Each has a test in the task named.

1. **A Los Angeles ZIP with an unlisted prefix** (90134, 90140, 90189, 93063). Plans must show *unpriced*, never priced from a guessed area, and never "free". *Task 8.*
2. **A Bronze request in California.** Every CA bronze plan is `Expanded Bronze`, so a `Bronze` filter must match it, or the user sees "nothing matched". *Task 3.*
3. **A ZIP outside a partial-county service area.** A plan sold only in some ZIPs of a county must not be listed for other ZIPs in that county. *Task 8.*
4. **November, when 2027 is on sale but only 2026 California data exists.** The answer must lead with the prior-year label and point to Covered California. *Tasks 8 and 9.*
5. **A plan filed in one rating area but listed in a multi-area service area** (Western Health Advantage). It must not be offered in counties it has no rate for. *Task 7.*

---

## PR 1 — SP0: exchanges, source registry, Bronze and wording fixes (Tasks 1–3)

### Task 1: Exchanges and the plan year on sale

**Files:**
- Create: `src/core/exchanges.py`
- Create: `src/core/plan_year.py`
- Test: `tests/test_exchanges.py`

**Interfaces:**
- Produces:
  - `Exchange(name: str, url: str)`, a frozen dataclass
  - `HEALTHCARE_GOV: Exchange`
  - `FILED_RATE_STATES: dict[str, Exchange]`
  - `CATALOG_STATES: tuple[str, ...]`
  - `exchange_for(state: str | None) -> Exchange | None`
  - `plan_year_on_sale(on: date) -> int`

- [ ] **Step 1: Write the failing test** — `tests/test_exchanges.py`

```python
"""Which exchange sells a state's plans, and which plan year is on sale."""
from datetime import date

import pytest

from src.core.exchanges import CATALOG_STATES, FILED_RATE_STATES, HEALTHCARE_GOV, exchange_for
from src.core.marketplace_api import MARKETPLACE_STATES
from src.core.plan_year import plan_year_on_sale


def test_each_state_is_sent_to_the_exchange_that_sells_its_plans():
    assert exchange_for("TX") == HEALTHCARE_GOV
    assert exchange_for("CA").name == "Covered California"
    assert exchange_for("CA").url == "https://www.coveredca.com/"
    # A state running its own exchange that PolicyPal has no data for: no name to give.
    assert exchange_for("NY") is None
    assert exchange_for(None) is None


def test_the_catalog_states_are_the_api_states_plus_the_filed_rate_ones():
    assert set(CATALOG_STATES) == set(MARKETPLACE_STATES) | {"CA"}
    assert not set(FILED_RATE_STATES) & set(MARKETPLACE_STATES)
    assert len(MARKETPLACE_STATES) == 30


@pytest.mark.parametrize("on, year", [
    (date(2026, 10, 31), 2026),
    (date(2026, 11, 1), 2027),
    (date(2026, 12, 31), 2027),
    (date(2027, 1, 15), 2027),
])
def test_next_years_plans_go_on_sale_on_november_1(on, year):
    assert plan_year_on_sale(on) == year
```

- [ ] **Step 2: Run it and check it fails**

Run: `uv run pytest tests/test_exchanges.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.exchanges'`

- [ ] **Step 3: Implement** — `src/core/exchanges.py`

```python
"""The exchange that sells each state's plans, and how PolicyPal prices them.

HealthCare.gov states are priced live through the CMS Marketplace API. A
filed-rate state runs its own exchange, which that API does not serve; its
plans and premiums come from CMS's state-based exchange PUF instead (ADR 0024).
A state in neither has no plan data here.
"""
from dataclasses import dataclass

from src.core.marketplace_api import MARKETPLACE_STATES


@dataclass(frozen=True)
class Exchange:
    name: str
    url: str


HEALTHCARE_GOV = Exchange("HealthCare.gov", "https://www.healthcare.gov/")

# Linked, never read: Covered California's Terms of Use forbid automated
# access (see the `coveredca` entry in src/ingestion/sources/registry.toml).
FILED_RATE_STATES: dict[str, Exchange] = {
    "CA": Exchange("Covered California", "https://www.coveredca.com/"),
}

CATALOG_STATES: tuple[str, ...] = MARKETPLACE_STATES + tuple(FILED_RATE_STATES)


def exchange_for(state: str | None) -> Exchange | None:
    if state in FILED_RATE_STATES:
        return FILED_RATE_STATES[state]
    if state in MARKETPLACE_STATES:
        return HEALTHCARE_GOV
    return None
```

`src/core/plan_year.py`

```python
"""The plan year on sale: next year's plans go on sale when open enrollment opens."""
from datetime import date

# HealthCare.gov and Covered California both open on November 1.
_OPEN_ENROLLMENT_OPENS = (11, 1)


def plan_year_on_sale(on: date) -> int:
    return on.year + 1 if (on.month, on.day) >= _OPEN_ENROLLMENT_OPENS else on.year
```

- [ ] **Step 4: Run it and check it passes**

Run: `uv run pytest tests/test_exchanges.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit.** Add a CHANGELOG bullet under `### Added`: "`src/core/exchanges.py` and `src/core/plan_year.py`: which exchange sells each state's plans, and the plan year on sale (from 1 November, next year's)."

```bash
git add src/core/exchanges.py src/core/plan_year.py tests/test_exchanges.py CHANGELOG.md
git commit -m "Name the exchange that sells each state's plans"
```

---

### Task 2: The source registry

**Files:**
- Create: `src/ingestion/sources/registry.toml`
- Create: `src/ingestion/sources/registry.py`
- Modify: `src/ingestion/sources/base.py` (add `registry_id`)
- Modify: `src/ingestion/sources/wikipedia.py` and `src/ingestion/sources/healthcare_gov.py` (set `registry_id`)
- Modify: `src/ingestion/sources/__init__.py` (`ALL_SOURCES`, `enabled_sources`)
- Create: `docs/decisions/0025-a-committed-source-registry.md`
- Test: `tests/test_registry.py`

**Interfaces:**
- Produces:
  - `load_registry(path: Path = REGISTRY_PATH) -> dict[str, RegisteredSource]` (raises `RegistryError`)
  - `require_enabled(source_id: str) -> RegisteredSource` (raises `SourceNotApprovedError`)
  - `is_enabled(source_id: str) -> bool`
  - `ALL_SOURCES: list[Source]`
  - `enabled_sources(sources) -> list[Source]`
  - `SOURCES` stays the name the pipeline and `chunk.py` import, now filtered.

- [ ] **Step 1: Write the failing test** — `tests/test_registry.py`

```python
"""The committed source registry: what PolicyPal reads, and whether it may (ADR 0025)."""
import pytest

from src.ingestion.sources import ALL_SOURCES, SOURCES, enabled_sources
from src.ingestion.sources.base import Source
from src.ingestion.sources.registry import (
    RegistryError,
    SourceNotApprovedError,
    load_registry,
    require_enabled,
)

_VALID = """
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


def _write(tmp_path, text):
    path = tmp_path / "registry.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_committed_registry_is_valid():
    registry = load_registry()

    assert {"wikipedia", "healthcare_gov", "cms_marketplace_api", "cms_ca_sbe_puf",
            "cms_ca_rating_areas", "coveredca"} <= set(registry)


def test_every_corpus_source_in_the_code_is_registered():
    registry = load_registry()

    assert all(source.registry_id in registry for source in ALL_SOURCES)
    assert [s.registry_id for s in SOURCES] == ["wikipedia", "healthcare_gov"]


def test_covered_california_is_recorded_as_link_only_and_refused():
    coveredca = load_registry()["coveredca"]

    assert (coveredca.enabled, coveredca.permission_status, coveredca.access) == (False, "denied", "link")
    with pytest.raises(SourceNotApprovedError):
        require_enabled("coveredca")


def test_an_unregistered_source_is_refused():
    with pytest.raises(SourceNotApprovedError):
        require_enabled("no_such_source")


def test_only_an_approved_permission_can_be_enabled(tmp_path):
    path = _write(tmp_path, _VALID.format(id="x", permission="pending_review", enabled="true"))

    with pytest.raises(RegistryError, match="x: enabled needs permission_status"):
        load_registry(path)


def test_a_missing_field_or_unknown_value_is_named(tmp_path):
    missing = _write(tmp_path, _VALID.format(id="x", permission="denied", enabled="false")
                     .replace('removal = "Disable it."\n', ""))
    with pytest.raises(RegistryError, match="x: missing removal"):
        load_registry(missing)

    unknown = _write(tmp_path, _VALID.format(id="x", permission="denied", enabled="false")
                     .replace('kind = "corpus"', 'kind = "website"'))
    with pytest.raises(RegistryError, match="x: kind 'website'"):
        load_registry(unknown)


def test_robots_must_have_been_checked_unless_it_does_not_apply(tmp_path):
    path = _write(tmp_path, _VALID.format(id="x", permission="denied", enabled="false")
                  .replace("robots_checked_on = 2026-09-24\n", ""))

    with pytest.raises(RegistryError, match="x: robots_checked_on"):
        load_registry(path)


def test_duplicate_ids_are_refused(tmp_path):
    entry = _VALID.format(id="x", permission="denied", enabled="false")

    with pytest.raises(RegistryError, match="duplicate id 'x'"):
        load_registry(_write(tmp_path, entry + entry))


def test_a_disabled_source_is_left_out_of_the_run():
    class _Denied(Source):
        name = registry_id = "coveredca"

        def fetch(self): ...
        def normalize(self): ...
        def chunk_documents(self): return []

    assert enabled_sources([_Denied()]) == []
```

- [ ] **Step 2: Run it and check it fails**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL with `ImportError: cannot import name 'ALL_SOURCES'`

- [ ] **Step 3: Implement the registry** — `src/ingestion/sources/registry.toml`

```toml
# Every source PolicyPal reads or links, and whether it may be used (ADR 0025).
# `enabled = true` needs permission_status public_domain, open_license or
# written_permission; registry.py refuses anything else at import time.
# Record a refused source too, disabled, so the decision is not re-litigated.

[[source]]
id = "wikipedia"
name = "Wikipedia articles on insurance"
publisher = "Wikimedia Foundation and Wikipedia contributors"
scope_urls = ["https://en.wikipedia.org/wiki/"]
kind = "corpus"
jurisdiction = "US"
license = "CC BY-SA 4.0"
license_url = "https://creativecommons.org/licenses/by-sa/4.0/"
permission_status = "open_license"
commercial_use = "yes"
robots = "not_applicable"
access = "api"
verified_on = 2026-09-24
enabled = true
removal = "Set enabled = false, then `make ingest` to rebuild the corpus and its BM25 index without it."
notes = "Read through the MediaWiki API (wikipedia-api), not crawled. Commercial use is allowed with attribution and share-alike on redistributed text."

[[source]]
id = "healthcare_gov"
name = "HealthCare.gov glossary and articles"
publisher = "Centers for Medicare & Medicaid Services"
scope_urls = ["https://www.healthcare.gov/api/"]
kind = "corpus"
jurisdiction = "US"
license = "US government work, 17 U.S.C. § 105"
license_url = "https://www.law.cornell.edu/uscode/text/17/105"
permission_status = "public_domain"
commercial_use = "yes"
robots = "not_applicable"
access = "api"
verified_on = 2026-09-24
enabled = true
removal = "Set enabled = false, then `make ingest`."
notes = "ADR 0003."

[[source]]
id = "cms_marketplace_api"
name = "CMS Marketplace API"
publisher = "Centers for Medicare & Medicaid Services"
scope_urls = ["https://marketplace.api.healthcare.gov/api/v1/"]
kind = "catalog"
jurisdiction = "US"
license = "US government work, 17 U.S.C. § 105; API key terms"
license_url = "https://developer.cms.gov/marketplace-api/"
permission_status = "public_domain"
commercial_use = "yes"
robots = "not_applicable"
access = "api"
verified_on = 2026-09-24
enabled = true
removal = "Delete plans where catalog_source = 'cms_api', and unset CMS_MARKETPLACE_API_KEY."
notes = "The 30 HealthCare.gov states only (MARKETPLACE_STATES). ADR 0009, 0010."

[[source]]
id = "cms_ca_sbe_puf"
name = "CMS state-based exchange PUF, California"
publisher = "Centers for Medicare & Medicaid Services"
scope_urls = ["https://www.cms.gov/files/zip/californiasbpuf2026.zip"]
kind = "catalog"
jurisdiction = "CA"
license = "US government work, 17 U.S.C. § 105"
license_url = "https://www.cms.gov/marketplace/resources/data/state-based-public-use-files"
permission_status = "public_domain"
commercial_use = "yes"
robots = "not_applicable"
access = "download"
verified_on = 2026-09-24
enabled = true
removal = "Delete plans where catalog_source = 'ca_sbe_puf' (cascades to counties, cost shares and rates), and delete the CA rows of rating_areas."
notes = "One published file per plan year, downloaded by URL. SBC, brochure, formulary and network URL columns are empty. ADR 0024."

[[source]]
id = "cms_ca_rating_areas"
name = "California geographic rating areas"
publisher = "Centers for Medicare & Medicaid Services"
scope_urls = ["https://www.cms.gov/cciio/programs-and-initiatives/health-insurance-market-reforms/ca-gra"]
kind = "catalog"
jurisdiction = "CA"
license = "US government work, 17 U.S.C. § 105"
license_url = "https://www.law.cornell.edu/uscode/text/17/105"
permission_status = "public_domain"
commercial_use = "yes"
robots = "not_applicable"
access = "manual"
verified_on = 2026-09-24
enabled = true
removal = "Remove src/ingestion/ca_puf/rating_areas.py and its uses."
notes = "Transcribed by hand into src/ingestion/ca_puf/rating_areas.py; re-check yearly (docs/runbooks/california.md)."

[[source]]
id = "coveredca"
name = "Covered California website"
publisher = "Covered California (California Health Benefit Exchange)"
scope_urls = ["https://www.coveredca.com/", "https://apply.coveredca.com/", "https://hbex.coveredca.com/"]
kind = "corpus"
jurisdiction = "CA"
license = "All rights reserved"
license_url = "https://www.coveredca.com/pdfs/privacy/Terms_of_Use.pdf"
permission_status = "denied"
commercial_use = "no"
robots = "allowed"
robots_checked_on = 2026-09-24
access = "link"
verified_on = 2026-09-24
enabled = false
removal = "Nothing is stored; remove the links in src/core/exchanges.py and frontend/src/features/plans/exchanges.js."
notes = "Linked, never read. Its Terms of Use forbid access 'through any automated means (including... scripts, web crawlers, or screen scrapers)' and downloading or republishing without a separate written agreement. robots.txt allows everything, but the Terms govern."
```

`src/ingestion/sources/registry.py`

```python
"""The committed source registry (ADR 0025): every source, and whether it may be used.

Read with the standard library's tomllib. An invalid registry fails at
import, so a bad edit cannot quietly enable a source.
"""
import tomllib
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name("registry.toml")

KINDS = {"corpus", "catalog", "sbc_host", "directory"}
PERMISSIONS = {"public_domain", "open_license", "written_permission", "pending_review", "denied"}
APPROVED = {"public_domain", "open_license", "written_permission"}
COMMERCIAL_USE = {"yes", "no", "review"}
ROBOTS = {"allowed", "disallowed", "unavailable", "not_applicable"}
ACCESS = {"api", "download", "crawl", "manual", "link"}
_REQUIRED = ("id", "name", "publisher", "scope_urls", "kind", "jurisdiction", "license", "license_url",
             "permission_status", "commercial_use", "robots", "access", "verified_on", "enabled",
             "removal", "notes")
_CHOICES = {"kind": KINDS, "permission_status": PERMISSIONS, "commercial_use": COMMERCIAL_USE,
            "robots": ROBOTS, "access": ACCESS}


class RegistryError(ValueError):
    """The registry file breaks a rule; the message names the entry and field."""


class SourceNotApprovedError(Exception):
    """A source that is unregistered or disabled was asked for."""


@dataclass(frozen=True)
class RegisteredSource:
    id: str
    name: str
    publisher: str
    scope_urls: tuple[str, ...]
    kind: str
    jurisdiction: str
    license: str
    license_url: str
    permission_status: str
    commercial_use: str
    robots: str
    robots_checked_on: date | None
    access: str
    verified_on: date
    enabled: bool
    removal: str
    notes: str


def _entry(raw: dict) -> RegisteredSource:
    label = raw.get("id", "<no id>")
    for field in _REQUIRED:
        if field not in raw:
            raise RegistryError(f"{label}: missing {field}")
    for field, allowed in _CHOICES.items():
        if raw[field] not in allowed:
            raise RegistryError(f"{label}: {field} {raw[field]!r} is not one of {sorted(allowed)}")
    if raw["robots"] != "not_applicable" and not isinstance(raw.get("robots_checked_on"), date):
        raise RegistryError(f"{label}: robots_checked_on is required when robots is {raw['robots']!r}")
    if not isinstance(raw["verified_on"], date):
        raise RegistryError(f"{label}: verified_on must be a date")
    if raw["enabled"] is True and raw["permission_status"] not in APPROVED:
        raise RegistryError(f"{label}: enabled needs permission_status in {sorted(APPROVED)}")
    jurisdiction = raw["jurisdiction"]
    if not (isinstance(jurisdiction, str) and len(jurisdiction) == 2 and jurisdiction.isupper()):
        raise RegistryError(f"{label}: jurisdiction must be 'US' or a state code")
    return RegisteredSource(**{**raw, "scope_urls": tuple(raw["scope_urls"]),
                               "robots_checked_on": raw.get("robots_checked_on")})


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, RegisteredSource]:
    with open(path, "rb") as handle:
        entries = tomllib.load(handle).get("source", [])
    registry: dict[str, RegisteredSource] = {}
    for raw in entries:
        unknown = set(raw) - set(_REQUIRED) - {"robots_checked_on"}
        if unknown:
            raise RegistryError(f"{raw.get('id', '<no id>')}: unknown field {sorted(unknown)[0]}")
        entry = _entry(raw)
        if entry.id in registry:
            raise RegistryError(f"duplicate id {entry.id!r}")
        registry[entry.id] = entry
    return registry


@cache
def _committed() -> dict[str, RegisteredSource]:
    return load_registry()


def is_enabled(source_id: str) -> bool:
    entry = _committed().get(source_id)
    return entry is not None and entry.enabled


def require_enabled(source_id: str) -> RegisteredSource:
    entry = _committed().get(source_id)
    if entry is None:
        raise SourceNotApprovedError(f"{source_id} is not in the source registry")
    if not entry.enabled:
        raise SourceNotApprovedError(f"{source_id} is disabled ({entry.permission_status})")
    return entry
```

Add a `registry_id` to `src/ingestion/sources/base.py`, just below the `name: str` attribute:

```python
    #: Its entry in registry.toml (ADR 0025); a source without one never runs.
    registry_id: str
```

In `src/ingestion/sources/wikipedia.py`, inside `class WikipediaSource(Source):`, add `registry_id = "wikipedia"` next to its `name`. In `src/ingestion/sources/healthcare_gov.py`, add `registry_id = "healthcare_gov"` under `name = "healthcare_gov"`.

Replace the body of `src/ingestion/sources/__init__.py`:

```python
"""Registered corpus sources, run in order by the ingestion pipeline.

Adding a corpus means writing one `Source` subclass, appending it to
ALL_SOURCES, and giving it an entry in registry.toml (ADR 0025). A source the
registry does not enable is left out of SOURCES, so it is never fetched,
chunked or embedded.
"""
from .base import Source
from .healthcare_gov import HealthCareGovSource
from .registry import is_enabled
from .wikipedia import WikipediaSource

ALL_SOURCES: list[Source] = [
    WikipediaSource(),
    HealthCareGovSource(),
]


def enabled_sources(sources: list[Source]) -> list[Source]:
    return [source for source in sources if is_enabled(source.registry_id)]


SOURCES: list[Source] = enabled_sources(ALL_SOURCES)

__all__ = ["ALL_SOURCES", "SOURCES", "HealthCareGovSource", "Source", "WikipediaSource", "enabled_sources"]
```

- [ ] **Step 4: Run it, and the existing pipeline tests, and check they pass**

Run: `uv run pytest tests/test_registry.py tests/test_ingestion_pipeline.py tests/test_sources_healthcare_gov.py -v`
Expected: all pass. `_FakeSource` in `test_ingestion_pipeline.py` patches `SOURCES` directly, so it needs no `registry_id`.

- [ ] **Step 5: Write ADR 0025** — `docs/decisions/0025-a-committed-source-registry.md`. Follow the heading layout of ADR 0021: Status, Context, Decision, Consequences.
  - **Context:** the pilot may go commercial; licences differ per source; ADR 0003 and 0013 recorded decisions in prose only.
  - **Decision:**
    - the TOML fields and allowed values, verbatim from `registry.py`;
    - only approved permissions may be enabled;
    - refused sources are recorded disabled;
    - `SOURCES` is filtered at import.
  - **Consequences:** a new source cannot run without an entry; removal is documented per entry; the registry is data, not proof of permission, so a commercial launch still needs legal review of every `enabled` entry.

- [ ] **Step 6: Commit.** Add a CHANGELOG bullet: "A committed source registry (`src/ingestion/sources/registry.toml`, ADR 0025): every source with its licence, permission, robots status and removal steps. Only approved sources run; Covered California is recorded as link-only."

```bash
git add src/ingestion/sources/ tests/test_registry.py docs/decisions/0025-a-committed-source-registry.md CHANGELOG.md
git commit -m "Record every source's licence and permission, and run only approved ones"
```

---

### Task 3: Bronze matches Expanded Bronze; name the right exchange

**Files:**
- Modify: `src/services/plan_search.py:201-202` (metal filter)
- Modify: `src/services/tools.py` (`_render`, `_plan_row`)
- Modify: `src/services/generation.py:44-81` (`PLAN_TOOL_PROMPT`) and `:131` (`COVERAGE_PROMPT` tail)
- Modify: `src/services/sbc_status.py:18` (`REASONS["no_link"]`)
- Test: `tests/test_plan_search.py`, `tests/test_tools.py`, `tests/test_generation.py`

**Interfaces:**
- Consumes: `exchange_for` (Task 1).
- Produces: search_plans tool results carry `"exchange": {"name": str, "url": str}` whenever the state has one. Task 9 relies on that key.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan_search.py`:

```python
def test_a_bronze_search_includes_expanded_bronze(session):
    """Every California bronze plan, and many elsewhere, is "Expanded Bronze";
    asked for bronze, the user must see them, not "nothing matched"."""
    _write_zip_counties(session, [County("TX", "99001", "Alpha", ("00001",))], YEAR)
    _write_county(session, [
        _plan("11111TX0010001", 300, metal_level="Bronze"),
        _plan("11111TX0010002", 310, metal_level="Expanded Bronze"),
        _plan("11111TX0010003", 320, metal_level="Silver"),
    ], "99001", YEAR)

    bronze, _ = _search(session, filters=PlanFilters(metal_level="Bronze"))
    expanded, _ = _search(session, filters=PlanFilters(metal_level="Expanded Bronze"))

    assert [p.hios_plan_id for p in bronze.plans] == ["11111TX0010001", "11111TX0010002"]
    assert [p.hios_plan_id for p in expanded.plans] == ["11111TX0010002"]
```

Append to `tests/test_tools.py`. Check the existing imports first: `PlanSearchResult`, `CountyOption`, `patch`, `json` and `_args` are already used in this file.

```python
def test_a_state_running_its_own_exchange_is_named_with_that_exchange():
    for state, exchange in (("CA", {"name": "Covered California", "url": "https://www.coveredca.com/"}),
                            ("NY", None)):
        result = PlanSearchResult("not_marketplace_state", state=state)
        with patch("src.services.tools.search_plans", return_value=result), patch("src.services.tools.get_session"):
            payload = json.loads(run_tool("search_plans", _args(zip_code="90012", age=40)).content)
        assert payload.get("exchange") == exchange
        assert payload["state"] == state


def test_a_plan_list_names_the_exchange_that_sells_those_plans():
    result = PlanSearchResult(
        "ok", total_matching=1, plan_year=2026, county=CountyOption("48001", "Anderson", "TX"),
        plans=(_result_plan("11111TX0010001", live=True),),
    )
    with patch("src.services.tools.search_plans", return_value=result), patch("src.services.tools.get_session"):
        payload = json.loads(run_tool("search_plans", _args(zip_code="75801", age=34)).content)

    assert payload["exchange"] == {"name": "HealthCare.gov", "url": "https://www.healthcare.gov/"}
```

Append to `tests/test_generation.py`:

```python
def test_no_prompt_sends_every_state_to_healthcare_gov():
    """21 states and DC run their own exchange; the result names the right one."""
    from src.services.generation import COVERAGE_PROMPT, PLAN_TOOL_PROMPT
    from src.services.sbc_status import REASONS

    for text in (PLAN_TOOL_PROMPT, COVERAGE_PROMPT, REASONS["no_link"]):
        assert "HealthCare.gov" not in text
    assert "exchange named in the result" in PLAN_TOOL_PROMPT
```

- [ ] **Step 2: Run them and check they fail**

Run: `uv run pytest tests/test_plan_search.py::test_a_bronze_search_includes_expanded_bronze tests/test_tools.py -k "exchange" tests/test_generation.py::test_no_prompt_sends_every_state_to_healthcare_gov -v`
Expected: 4 FAIL. The Bronze search returns only `…0001`, `exchange` is missing, and HealthCare.gov is in the prompt.

- [ ] **Step 3: Implement**

In `src/services/plan_search.py`, add a constant under `_CATASTROPHIC_MAX_AGE`:

```python
# CMS sells "Expanded Bronze" (a bronze plan above the usual value range) as
# bronze; every California bronze plan is one. Asked for bronze, show both.
_BRONZE_LEVELS = ("Bronze", "Expanded Bronze")
```

and replace

```python
    if filters.metal_level:
        conditions.append(Plan.metal_level == filters.metal_level)
```

with

```python
    if filters.metal_level == "Bronze":
        conditions.append(Plan.metal_level.in_(_BRONZE_LEVELS))
    elif filters.metal_level:
        conditions.append(Plan.metal_level == filters.metal_level)
```

In `src/services/tools.py`, add `from src.core.exchanges import exchange_for` and this helper above `_render`:

```python
def _exchange(state: str | None) -> dict:
    """The exchange that sells the state's plans, or nothing when there is none to name."""
    exchange = exchange_for(state)
    return {"exchange": {"name": exchange.name, "url": exchange.url}} if exchange else {}
```

Change the first line of `_render`:

```python
    if result.status == "not_marketplace_state":
        return _outcome(result.status, state=result.state, **_exchange(result.state))
```

and add to the `ok` payload dict, after `"county"`:

```python
        **_exchange(result.county.state),
```

In `_plan_row`, only name a reference premium that exists. California plans have none. Change

```python
    if not plan.premium_is_live:
```

to

```python
    if not plan.premium_is_live and plan.premium_reference is not None:
```

In `src/services/generation.py` `PLAN_TOOL_PROMPT`, make three replacements:
1. `"plans from HealthCare.gov, and plan_coverage,"` becomes `"plans from CMS data for each state's exchange, and plan_coverage,"`.
2. `"say that a tax credit may lower it and that HealthCare.gov gives the price they would pay."` becomes `"say that a tax credit may lower it and that the exchange named in the result gives the price they would pay."`
3. `"not_marketplace_state — that state runs its own exchange, so its plans are not in this data, point to HealthCare.gov;"` becomes `"not_marketplace_state — that state runs its own exchange, so its plans are not in this data: point to the exchange named in the result, or to the state's own exchange if none is named;"`.

In `COVERAGE_PROMPT`, replace `"otherwise point to HealthCare.gov;"` with `"otherwise point to the exchange for the plan's state;"`.

In `src/services/sbc_status.py`, set `"no_link": "no Summary of Benefits and Coverage link is listed for this plan",`.

- [ ] **Step 4: Run the affected suites and check they pass**

Run: `uv run pytest tests/test_plan_search.py tests/test_tools.py tests/test_generation.py tests/test_plan_coverage.py -v`
Expected: all pass. If an existing test asserted the old `no_link` sentence, update it to the new sentence; the meaning is unchanged.

- [ ] **Step 5: Commit and push PR 1's scope.** Add CHANGELOG bullets under `### Fixed`:
  - "A Bronze plan search now includes Expanded Bronze plans, which it silently missed; every California bronze plan is one."
  - "Plan answers name the exchange that sells the state's plans instead of always sending people to HealthCare.gov, which is wrong for the 21 states and DC that run their own."

```bash
git add src/services/ tests/test_plan_search.py tests/test_tools.py tests/test_generation.py CHANGELOG.md
git commit -m "Count Expanded Bronze as bronze, and name each state's own exchange"
make check && git push
```

Expected: `make check` is green. This is the SP0 checkpoint: the registry and fixes are done, and no data has changed.

---

## PR 1 continues — SP1: California plan comparison (Tasks 4–12)

The spec allowed "two PRs, or a stacked branch". Keep one branch and one PR (#38) unless the reviewer asks to split. PR #38's description lists both parts.

### Task 4: Schema — catalog source, ZIP-level service areas, rating areas, filed rates, loads

**Files:**
- Modify: `src/models/plan.py`
- Create: `migrations/versions/<generated>_add_filed_rate_catalog.py`
- Test: `tests/test_models_plan.py` (new)

**Interfaces:**
- Produces:
  - `Plan.catalog_source: str`, `'cms_api'` or `'ca_sbe_puf'`
  - `PlanCounty.zipcodes: list[str] | None`
  - `RatingArea(state, plan_year, countyfips, zip3, rating_area)`
  - `PlanRate(plan_id, rating_area, age, individual_rate)`
  - `CatalogLoad(source, state, plan_year, file_url, file_label, sha256, plans, loaded_at)`

- [ ] **Step 1: Write the failing test** — `tests/test_models_plan.py`

```python
"""The filed-rate catalog tables (ADR 0024)."""
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.plan import CatalogLoad, Issuer, Plan, PlanCounty, PlanRate, RatingArea


def _plan(session, source="ca_sbe_puf"):
    issuer = Issuer(hios_issuer_id="99999", plan_year=1999, name="Test", state="CA")
    session.add(issuer)
    session.flush()
    plan = Plan(issuer_id=issuer.id, hios_plan_id="99999CA0010001", plan_year=1999, marketing_name="P",
                metal_level="Silver", plan_type="HMO", state="CA", hsa_eligible=False,
                has_national_network=False, catalog_source=source)
    session.add(plan)
    session.flush()
    return plan


def test_a_plan_defaults_to_the_api_catalog_and_accepts_only_known_sources(session):
    issuer = Issuer(hios_issuer_id="99998", plan_year=1999, name="Test", state="TX")
    session.add(issuer)
    session.flush()
    api = Plan(issuer_id=issuer.id, hios_plan_id="99998TX0010001", plan_year=1999, marketing_name="P",
               metal_level="Silver", plan_type="HMO", state="TX", hsa_eligible=False, has_national_network=False)
    session.add(api)
    session.flush()
    session.refresh(api)
    assert api.catalog_source == "cms_api"

    with pytest.raises(IntegrityError):
        _plan(session, source="scraped")


def test_a_plan_county_may_be_limited_to_some_zips(session):
    plan = _plan(session)
    session.add_all([PlanCounty(plan_id=plan.id, countyfips="06037", zipcodes=["90001", "90002"]),
                     PlanCounty(plan_id=plan.id, countyfips="06059")])
    session.flush()

    rows = {c.countyfips: c.zipcodes for c in session.query(PlanCounty).filter_by(plan_id=plan.id)}
    assert rows == {"06037": ["90001", "90002"], "06059": None}


def test_a_rate_is_one_per_plan_area_and_age_and_ages_are_14_to_64(session):
    plan = _plan(session)
    session.add(PlanRate(plan_id=plan.id, rating_area=16, age=40, individual_rate=Decimal("512.34")))
    session.flush()

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(PlanRate(plan_id=plan.id, rating_area=16, age=40, individual_rate=Decimal("1")))
            session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(PlanRate(plan_id=plan.id, rating_area=16, age=65, individual_rate=Decimal("1")))
            session.flush()


def test_rates_go_with_their_plan(session):
    plan = _plan(session)
    session.add(PlanRate(plan_id=plan.id, rating_area=1, age=14, individual_rate=Decimal("300.00")))
    session.flush()

    plan_id = plan.id
    session.delete(plan)
    session.flush()

    assert session.query(PlanRate).filter_by(plan_id=plan_id).count() == 0


def test_a_rating_area_row_is_unique_per_year_county_and_zip3(session):
    session.add_all([RatingArea(state="CA", plan_year=1999, countyfips="06037", zip3="900", rating_area=16),
                     RatingArea(state="CA", plan_year=1999, countyfips="06059", rating_area=18)])
    session.flush()
    assert session.query(RatingArea).filter_by(plan_year=1999, countyfips="06059").one().zip3 == ""

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(RatingArea(state="CA", plan_year=1999, countyfips="06059", rating_area=17))
            session.flush()


def test_a_load_is_recorded(session):
    session.add(CatalogLoad(source="ca_sbe_puf", state="CA", plan_year=1999, file_url="file:test.zip",
                            file_label="01011999", sha256="0" * 64, plans=1))
    session.flush()
    assert session.query(CatalogLoad).filter_by(plan_year=1999).one().loaded_at is not None
```

- [ ] **Step 2: Run it and check it fails**

Run: `uv run pytest tests/test_models_plan.py -v`
Expected: FAIL with `ImportError: cannot import name 'CatalogLoad'`

- [ ] **Step 3: Add the models** in `src/models/plan.py`.

Add `SmallInteger` to the `sqlalchemy` import list, and `ARRAY` to the dialect import: `from sqlalchemy.dialects.postgresql import ARRAY, UUID`.

In `Plan.__table_args__`, append:

```python
        CheckConstraint("catalog_source IN ('cms_api', 'ca_sbe_puf')", name="ck_plans_catalog_source"),
```

In `Plan`, after `network_url`, add:

```python
    # Which pipeline wrote the row (ADR 0024), so one source can be audited or removed.
    catalog_source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="cms_api")
```

In `PlanCounty`, after `countyfips`, add:

```python
    # Null: sold in the whole county, as every API-sourced row is. Otherwise
    # the only ZIPs it is sold in: a California "partial county" (ADR 0024).
    zipcodes: Mapped[list[str] | None] = mapped_column(ARRAY(String(5)), nullable=True)
```

Append these classes at the end of the file:

```python
class RatingArea(Base):
    """Which rating area a county, or one 3-digit ZIP prefix within it, prices in.

    Filed-rate states only (ADR 0024). `zip3` is '' for the whole county,
    never NULL: NULLs are distinct in a unique key, as `PlanCostShare` notes.
    A ZIP whose prefix has no row has no rating area, and is not priced.
    """

    __tablename__ = "rating_areas"
    __table_args__ = (
        UniqueConstraint("plan_year", "countyfips", "zip3", name="uq_rating_areas_plan_year_countyfips_zip3"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    plan_year: Mapped[int] = mapped_column(Integer, nullable=False)
    countyfips: Mapped[str] = mapped_column(String(5), nullable=False)
    zip3: Mapped[str] = mapped_column(String(3), nullable=False, server_default="", default="")
    rating_area: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class PlanRate(Base):
    """A filed monthly premium for one person: plan, rating area and age (ADR 0024).

    `age` 14 stands for CMS's 0-14 band and 64 for "64 and over"; a person's
    age is clamped into 14..64 to look one up.
    """

    __tablename__ = "plan_rates"
    __table_args__ = (
        UniqueConstraint("plan_id", "rating_area", "age", name="uq_plan_rates_plan_id_rating_area_age"),
        CheckConstraint("age BETWEEN 14 AND 64", name="ck_plan_rates_age"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
    )
    rating_area: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    age: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    individual_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class CatalogLoad(Base):
    """One load of a published catalog file: what, when, and exactly which bytes."""

    __tablename__ = "catalog_loads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    plan_year: Mapped[int] = mapped_column(Integer, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    # The date CMS stamps in its file names, e.g. 05052026.
    file_label: Mapped[str] = mapped_column(String(32), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    plans: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

`PlanRate` rows are deleted with their plan by the database's `ON DELETE CASCADE`. The ORM `session.delete(plan)` in the test relies on that `passive` behaviour, as `PlanCostShare` already does.

- [ ] **Step 4: Generate the migration and review it**

Run: `uv run alembic revision --autogenerate -m "add filed rate catalog"`

Expected: a new file `migrations/versions/2026MMDD_HHMM-<rev>_add_filed_rate_catalog.py` with `down_revision = "f6e50c4aec26"`. Edit it so that it contains exactly this. Keep the generated `revision` id, and add the docstring text.

```python
"""Add the filed-rate catalog: California plans from CMS's state-based exchange PUF (ADR 0024)

`plans.catalog_source` says which pipeline wrote a plan. `plan_counties.zipcodes`
limits a plan to some ZIPs of a county. `rating_areas`, `plan_rates` and
`catalog_loads` hold a filed-rate state's rating geography, premiums and
load history. The API path writes none of these, so its rows are unchanged.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "<keep the generated id>"
down_revision: str | Sequence[str] | None = "f6e50c4aec26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("catalog_source", sa.String(length=16), server_default="cms_api", nullable=False))
    op.create_check_constraint("ck_plans_catalog_source", "plans", "catalog_source IN ('cms_api', 'ca_sbe_puf')")
    op.add_column("plan_counties", sa.Column("zipcodes", postgresql.ARRAY(sa.String(length=5)), nullable=True))
    op.create_table(
        "rating_areas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("plan_year", sa.Integer(), nullable=False),
        sa.Column("countyfips", sa.String(length=5), nullable=False),
        sa.Column("zip3", sa.String(length=3), server_default="", nullable=False),
        sa.Column("rating_area", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_year", "countyfips", "zip3", name="uq_rating_areas_plan_year_countyfips_zip3"),
    )
    op.create_table(
        "plan_rates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("rating_area", sa.SmallInteger(), nullable=False),
        sa.Column("age", sa.SmallInteger(), nullable=False),
        sa.Column("individual_rate", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.CheckConstraint("age BETWEEN 14 AND 64", name="ck_plan_rates_age"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "rating_area", "age", name="uq_plan_rates_plan_id_rating_area_age"),
    )
    op.create_table(
        "catalog_loads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("plan_year", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_label", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("plans", sa.Integer(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("catalog_loads")
    op.drop_table("plan_rates")
    op.drop_table("rating_areas")
    op.drop_column("plan_counties", "zipcodes")
    op.drop_constraint("ck_plans_catalog_source", "plans", type_="check")
    op.drop_column("plans", "catalog_source")
```

- [ ] **Step 5: Migrate, round-trip, and run the tests**

Run: `make migrate && uv run alembic downgrade -1 && make migrate && uv run alembic check && uv run pytest tests/test_models_plan.py -v`
Expected: `No new upgrade operations detected.`, then 6 passed.

- [ ] **Step 6: Commit.** Add a CHANGELOG bullet: "Migration for a filed-rate plan catalog: `plans.catalog_source`, ZIP-limited `plan_counties.zipcodes`, and new `rating_areas`, `plan_rates` and `catalog_loads` tables."

```bash
git add src/models/plan.py migrations/versions/*add_filed_rate_catalog.py tests/test_models_plan.py CHANGELOG.md
git commit -m "Add tables for a catalog priced from filed rates"
```

---

### Task 5: California rating areas and issuers, curated

**Files:**
- Create: `src/ingestion/ca_puf/__init__.py` (empty docstring module)
- Create: `src/ingestion/ca_puf/rating_areas.py`
- Create: `src/ingestion/ca_puf/issuers.py`
- Test: `tests/test_ca_puf_curated.py`

**Interfaces:**
- Produces:
  - `LOS_ANGELES = "06037"`
  - `COUNTY_AREAS: dict[str, int]` (57 counties)
  - `LA_ZIP3_AREAS: dict[str, int]`
  - `county_area(countyfips) -> int` (raises `UnmappedCountyError`)
  - `area_for(countyfips, zipcode) -> int | None`
  - `table_rows(countyfips: Iterable[str]) -> list[tuple[str, str, int]]`, as `(countyfips, zip3, area)`
  - `CA_ISSUERS: dict[str, str]`
  - `issuer_name(hios_issuer_id) -> str` (raises `UnknownIssuerError`)

- [ ] **Step 1: Write the failing test** — `tests/test_ca_puf_curated.py`

```python
"""The hand-curated California data: rating areas and issuer names (ADR 0024)."""
import pytest

from src.ingestion.ca_puf.issuers import CA_ISSUERS, UnknownIssuerError, issuer_name
from src.ingestion.ca_puf.rating_areas import (
    COUNTY_AREAS,
    LA_ZIP3_AREAS,
    LOS_ANGELES,
    UnmappedCountyError,
    area_for,
    county_area,
    table_rows,
)


def test_every_california_county_but_los_angeles_has_one_area():
    assert len(COUNTY_AREAS) == 57
    assert LOS_ANGELES not in COUNTY_AREAS
    assert all(fips.startswith("06") and len(fips) == 5 for fips in COUNTY_AREAS)
    # Areas 15 and 16 are Los Angeles's alone.
    assert set(COUNTY_AREAS.values()) == set(range(1, 15)) | {17, 18, 19}


@pytest.mark.parametrize("fips, area", [
    ("06003", 1), ("06041", 2), ("06067", 3), ("06075", 4), ("06013", 5), ("06001", 6),
    ("06085", 7), ("06081", 8), ("06053", 9), ("06107", 10), ("06019", 11), ("06111", 12),
    ("06025", 13), ("06029", 14), ("06065", 17), ("06059", 18), ("06073", 19),
])
def test_counties_are_in_cmss_areas(fips, area):
    assert county_area(fips) == area


def test_los_angeles_splits_by_zip_prefix_and_an_unlisted_prefix_has_no_area():
    assert area_for(LOS_ANGELES, "90601") == 15
    assert area_for(LOS_ANGELES, "90012") == 16
    assert area_for(LOS_ANGELES, "93550") == 15
    # Real Los Angeles ZIPs whose prefix CMS lists in neither area: never guessed.
    for zipcode in ("90134", "90140", "90189", "93063"):
        assert area_for(LOS_ANGELES, zipcode) is None
    assert area_for("06059", "92602") == 18
    assert len(LA_ZIP3_AREAS) == 21


def test_a_county_missing_from_the_map_is_an_error_not_a_guess():
    with pytest.raises(UnmappedCountyError):
        county_area("06999")
    with pytest.raises(UnmappedCountyError):
        area_for("06999", "99999")


def test_table_rows_are_whole_county_rows_and_los_angeles_prefix_rows():
    rows = table_rows(["06059", LOS_ANGELES])

    assert ("06059", "", 18) in rows
    assert ("06037", "900", 16) in rows and ("06037", "935", 15) in rows
    assert not any(fips == LOS_ANGELES and zip3 == "" for fips, zip3, _ in rows)
    assert len(rows) == 1 + 21


def test_the_eleven_2026_issuers_are_named_and_an_unknown_one_is_refused():
    assert len(CA_ISSUERS) == 11
    assert issuer_name("40513") == "Kaiser Permanente"
    assert issuer_name("70285") == "Blue Shield of California"
    with pytest.raises(UnknownIssuerError):
        issuer_name("12345")
```

- [ ] **Step 2: Run it and check it fails**

Run: `uv run pytest tests/test_ca_puf_curated.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingestion.ca_puf'`

- [ ] **Step 3: Implement**

`src/ingestion/ca_puf/__init__.py`:

```python
"""California plans from CMS's state-based exchange PUF (ADR 0024): `make ingest-ca-plans`."""
```

`src/ingestion/ca_puf/rating_areas.py`:

```python
"""California's geographic rating areas, transcribed from CMS.

Source: https://www.cms.gov/cciio/programs-and-initiatives/health-insurance-market-reforms/ca-gra
Verified 2026-09-24 against the raw page, and against the 2026 PUF: every
plan's rated areas are areas where it is sold. Re-check yearly
(docs/runbooks/california.md).

Counties map to one area, except Los Angeles, which CMS splits by 3-digit ZIP
prefix. Some real Los Angeles ZIPs have a prefix in neither list (901, 930 in
2026): they have no area, and their plans are shown unpriced, never guessed.
"""
from collections.abc import Iterable

LOS_ANGELES = "06037"

_AREAS: dict[int, tuple[str, ...]] = {
    # Alpine, Del Norte, Siskiyou, Modoc, Lassen, Shasta, Trinity, Humboldt, Tehama, Plumas, Nevada,
    # Sierra, Mendocino, Lake, Butte, Glenn, Sutter, Yuba, Colusa, Amador, Calaveras, Tuolumne
    1: ("06003", "06015", "06093", "06049", "06035", "06089", "06105", "06023", "06103", "06063", "06057",
        "06091", "06045", "06033", "06007", "06021", "06101", "06115", "06011", "06005", "06009", "06109"),
    2: ("06055", "06097", "06095", "06041"),  # Napa, Sonoma, Solano, Marin
    3: ("06067", "06061", "06017", "06113"),  # Sacramento, Placer, El Dorado, Yolo
    4: ("06075",),  # San Francisco
    5: ("06013",),  # Contra Costa
    6: ("06001",),  # Alameda
    7: ("06085",),  # Santa Clara
    8: ("06081",),  # San Mateo
    9: ("06087", "06053", "06069"),  # Santa Cruz, Monterey, San Benito
    10: ("06077", "06099", "06047", "06043", "06107"),  # San Joaquin, Stanislaus, Merced, Mariposa, Tulare
    11: ("06039", "06019", "06031"),  # Madera, Fresno, Kings
    12: ("06079", "06083", "06111"),  # San Luis Obispo, Santa Barbara, Ventura
    13: ("06051", "06027", "06025"),  # Mono, Inyo, Imperial
    14: ("06029",),  # Kern
    17: ("06071", "06065"),  # San Bernardino, Riverside
    18: ("06059",),  # Orange
    19: ("06073",),  # San Diego
}

COUNTY_AREAS: dict[str, int] = {fips: area for area, counties in _AREAS.items() for fips in counties}

LA_ZIP3_AREAS: dict[str, int] = {
    **dict.fromkeys(("906", "907", "908", "910", "911", "912", "915", "917", "918", "935"), 15),
    **dict.fromkeys(("900", "902", "903", "904", "905", "913", "914", "916", "923", "928", "932"), 16),
}


class UnmappedCountyError(ValueError):
    """A California county the transcribed map does not have: fix the map, never guess."""


def county_area(countyfips: str) -> int:
    try:
        return COUNTY_AREAS[countyfips]
    except KeyError:
        raise UnmappedCountyError(f"county {countyfips} is not in the California rating-area map") from None


def area_for(countyfips: str, zipcode: str) -> int | None:
    """The rating area a ZIP in a county prices in; None for an unlisted Los Angeles prefix."""
    if countyfips == LOS_ANGELES:
        return LA_ZIP3_AREAS.get(zipcode[:3])
    return county_area(countyfips)


def table_rows(countyfips: Iterable[str]) -> list[tuple[str, str, int]]:
    """`(countyfips, zip3, area)` rows for `rating_areas`; zip3 '' means the whole county."""
    rows: list[tuple[str, str, int]] = []
    for fips in sorted(set(countyfips)):
        if fips == LOS_ANGELES:
            rows += [(fips, zip3, area) for zip3, area in sorted(LA_ZIP3_AREAS.items())]
        else:
            rows.append((fips, "", county_area(fips)))
    return rows
```

`src/ingestion/ca_puf/issuers.py`:

```python
"""Names of California's 2026 Covered California issuers, by HIOS issuer ID.

The PUF's ISSUER NAME column is blank on every row. These are curated:
- Covered California's 2026 carrier list (news release, 2025-08-14);
- matched to IDs by each issuer's network names and service-area footprint in
  the 2026 PUF (e.g. 84014 sells only in Santa Clara, Valley Health Plan's
  county).

Verified 2026-09-24. Cross-check against a federal issuer list before each
year's load (docs/runbooks/california.md).
"""

CA_ISSUERS: dict[str, str] = {
    "18126": "Molina Healthcare",
    "27603": "Anthem Blue Cross",
    "40513": "Kaiser Permanente",
    "47579": "Balance by CCHP",
    "51396": "Inland Empire Health Plan",
    "67138": "Health Net",
    "70285": "Blue Shield of California",
    "84014": "Valley Health Plan",
    "92499": "Sharp Health Plan",
    "92815": "L.A. Care Health Plan",
    "93689": "Western Health Advantage",
}


class UnknownIssuerError(ValueError):
    """An issuer the curated list does not name: add it, with its source, rather than guess."""


def issuer_name(hios_issuer_id: str) -> str:
    try:
        return CA_ISSUERS[hios_issuer_id]
    except KeyError:
        raise UnknownIssuerError(f"issuer {hios_issuer_id} is not in CA_ISSUERS") from None
```

- [ ] **Step 4: Run it and check it passes**

Run: `uv run pytest tests/test_ca_puf_curated.py -v`
Expected: 22 passed

- [ ] **Step 5: Commit.** Add a CHANGELOG bullet: "California's rating areas and its 11 issuer names, transcribed from CMS and checked against the 2026 PUF."

```bash
git add src/ingestion/ca_puf/ tests/test_ca_puf_curated.py CHANGELOG.md
git commit -m "Transcribe California's rating areas and issuer names"
```

---

### Task 6: Read the PUF zip (pure)

**Files:**
- Create: `src/ingestion/ca_puf/read.py`
- Create: `tests/ca_puf_fixtures.py` (synthetic zip builder)
- Test: `tests/test_ca_puf_read.py`

**Interfaces:**
- Produces:
  - `PufFormatError(ValueError)`
  - `puf_money(text: str) -> Decimal | None`
  - `age_key(text: str) -> int`
  - dataclasses `PufPlan`, `PufCostShare`, `PufServiceArea` and `Puf`, with fields exactly as in the code below
  - `read_puf(path: Path, year: int) -> Puf`
  - constants `NO_CSR`, `IN_NETWORK`, `INDIVIDUAL`
  - Test helper `write_puf(tmp_path, *, plans, rates, areas, label="01011999") -> Path`, and row builders `plan_row(...)`, `rate_row(...)`, `area_row(...)`

- [ ] **Step 1: Write the fixture builder** — `tests/ca_puf_fixtures.py`

```python
"""A synthetic California PUF zip: made-up rows in the real files' column shape.

Only the columns read.py reads. No real PUF rows are committed.
"""
import csv
import io
import zipfile

YEAR = 1999


def plan_row(plan_id, *, issuer="40513", name="Silver 70 HMO", metal="Silver", plan_type="HMO",
             variant="Standard Silver On Exchange Plan", area="CAS001", market="Individual", dental="No",
             qhp="On the Exchange", combined="", medical="$2,000 ", drug="$250", moop="$9,200 ", year=YEAR):
    return {
        "BUSINESS YEAR": str(year), "STATE CODE": "CA", "ISSUER ID": issuer, "MARKET COVERAGE": market,
        "DENTAL ONLY PLAN": dental, "QHP NONQHP TYPE ID": qhp, "STANDARD COMPONENT ID": plan_id[:14],
        "PLAN ID": plan_id, "PLAN MARKETING NAME": name, "PLAN TYPE": plan_type, "METAL LEVEL": metal,
        "IS HSA ELIGIBLE": "No", "NATIONAL NETWORK": "No", "SERVICE AREA ID": area,
        "CSR VARIATION TYPE": variant, "TEHB DED INN TIER 1 INDIVIDUAL": combined,
        "MEHB DED INN TIER1 INDIVIDUAL": medical, "DEHB DED INN TIER1 INDIVIDUAL": drug,
        "TEHB INN TIER 1 INDIVIDUAL MOOP": moop,
    }


def rate_row(plan_id, area, age, rate):
    return {"PLAN ID": plan_id, "RATING AREA ID": f"Rating Area {area}", "AGE": age, "INDIVIDUAL RATE": rate,
            "TOBACCO": "No Preference"}


def area_row(county, *, issuer="40513", area="CAS001", partial="", statewide="false",
             market="Individual", dental="No"):
    return {"ISSUER ID": issuer, "SERVICE AREA ID": area, "COVER ENTIRE STATE": statewide,
            "COUNTY": county, "PARTIAL COUNTY": "true" if partial else ("" if statewide == "true" else "false"),
            "ZIP CODE": partial, "MARKET COVERAGE": market, "DENTAL PLAN ONLY": dental}


def _csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def write_puf(tmp_path, *, plans, rates, areas, label="01011999"):
    path = tmp_path / "ca.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"CAPlans{label}.csv", _csv(plans))
        archive.writestr(f"CARates{label}.csv", _csv(rates))
        archive.writestr(f"CAServiceAreas{label}.csv", _csv(areas))
    return path
```

- [ ] **Step 2: Write the failing test** — `tests/test_ca_puf_read.py`

```python
"""Reading CMS's California state-based exchange PUF (ADR 0024). No database."""
from decimal import Decimal

import pytest

from src.ingestion.ca_puf.read import NO_CSR, PufFormatError, age_key, puf_money, read_puf
from tests.ca_puf_fixtures import YEAR, area_row, plan_row, rate_row, write_puf

BASE = "40513CA0010001"


def _puf(tmp_path, plans=None, rates=None, areas=None):
    return write_puf(
        tmp_path,
        plans=plans or [plan_row(f"{BASE}-01")],
        rates=rates or [rate_row(BASE, 16, "40", "512.34")],
        areas=areas or [area_row("Los Angeles - 06037")],
    )


@pytest.mark.parametrize("text, amount", [
    ("$5,200 ", Decimal("5200")), ("$0", Decimal("0")), ("412.55", Decimal("412.55")),
    ("", None), ("  ", None), ("Not Applicable", None),
])
def test_money_is_read_as_cms_writes_it(text, amount):
    assert puf_money(text) == amount


def test_text_that_is_not_money_is_refused():
    with pytest.raises(PufFormatError, match="not an amount"):
        puf_money("20% coinsurance")


@pytest.mark.parametrize("text, age", [("0-14", 14), ("15", 15), ("63", 63), ("64 and over", 64)])
def test_age_bands_become_ages(text, age):
    assert age_key(text) == age


def test_an_unknown_age_band_is_refused():
    with pytest.raises(PufFormatError):
        age_key("65")


def test_only_individual_on_exchange_medical_plans_are_kept(tmp_path):
    puf = read_puf(_puf(tmp_path, plans=[
        plan_row(f"{BASE}-01"),
        plan_row("40513CA0010002-01", market="SHOP (Small Group)"),
        plan_row("40513CA0010003-01", dental="Yes"),
        plan_row("40513CA0010004-00", qhp="Off the Exchange"),
    ]), YEAR)

    assert [p.hios_plan_id for p in puf.plans] == [BASE]
    assert puf.label == "01011999"


def test_a_plan_comes_from_its_standard_variant_and_expanded_bronze_is_kept(tmp_path):
    bronze = "40513CA0020001"
    puf = read_puf(_puf(tmp_path, plans=[
        plan_row(f"{bronze}-01", metal="Expanded Bronze", name="Bronze 60 HMO", variant="Standard Bronze On Exchange Plan"),
    ], rates=[rate_row(bronze, 16, "40", "400.00")]), YEAR)

    (plan,) = puf.plans
    assert (plan.hios_plan_id, plan.metal_level, plan.marketing_name, plan.issuer_id, plan.service_area_id) == (
        bronze, "Expanded Bronze", "Bronze 60 HMO", "40513", "CAS001")


def test_cost_shares_use_the_apis_words_for_the_standard_variant(tmp_path):
    puf = read_puf(_puf(tmp_path, plans=[
        plan_row(f"{BASE}-01", medical="$2,000 ", drug="$250", moop="$9,200 "),
        plan_row(f"{BASE}-06", variant="94% AV Level Silver Plan", medical="$0", drug="$0", moop="$1,400"),
    ]), YEAR)

    shares = {(s.csr_variant, s.cost_share_type): s.amount for s in puf.cost_shares}
    assert shares[(NO_CSR, "Medical EHB Deductible")] == Decimal("2000")
    assert shares[(NO_CSR, "Drug EHB Deductible")] == Decimal("250")
    assert shares[(NO_CSR, "Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)")] == Decimal("9200")
    assert shares[("94% AV Level Silver Plan", "Medical EHB Deductible")] == Decimal("0")
    # An empty column is no row, not a $0 deductible.
    assert (NO_CSR, "Combined Medical and Drug EHB Deductible") not in shares
    assert {s.hios_plan_id for s in puf.cost_shares} == {BASE}


def test_a_base_plan_with_no_standard_variant_is_refused(tmp_path):
    with pytest.raises(PufFormatError, match="no -01 row"):
        read_puf(_puf(tmp_path, plans=[plan_row(f"{BASE}-06", variant="94% AV Level Silver Plan")]), YEAR)


def test_service_areas_carry_county_zips_and_statewide_rows(tmp_path):
    puf = read_puf(_puf(tmp_path, areas=[
        area_row("Los Angeles - 06037", partial="90002, 90001"),
        area_row("Orange - 06059"),
        area_row("", statewide="true", area="CAS002"),
        area_row("Orange - 06059", market="SHOP (Small Group)"),
    ]), YEAR)

    assert [(a.countyfips, a.zipcodes, a.service_area_id) for a in puf.service_areas] == [
        ("06037", ("90001", "90002"), "CAS001"),
        ("06059", None, "CAS001"),
        (None, None, "CAS002"),
    ]


def test_rates_are_kept_only_for_kept_plans(tmp_path):
    puf = read_puf(_puf(tmp_path, rates=[
        rate_row(BASE, 16, "0-14", "300.00"),
        rate_row(BASE, 16, "64 and over", "1200.00"),
        rate_row("62683CA0010001", 16, "40", "30.00"),  # a dental plan's
    ]), YEAR)

    assert puf.rates == {(BASE, 16, 14): Decimal("300.00"), (BASE, 16, 64): Decimal("1200.00")}


def test_a_file_for_another_year_or_missing_a_column_is_refused(tmp_path):
    with pytest.raises(PufFormatError, match="plan year 2025"):
        read_puf(_puf(tmp_path, plans=[plan_row(f"{BASE}-01", year=2025)]), YEAR)

    row = plan_row(f"{BASE}-01")
    del row["PLAN MARKETING NAME"]
    with pytest.raises(PufFormatError, match="PLAN MARKETING NAME"):
        read_puf(_puf(tmp_path, plans=[row]), YEAR)
```

- [ ] **Step 3: Run it and check it fails**

Run: `uv run pytest tests/test_ca_puf_read.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingestion.ca_puf.read'`

- [ ] **Step 4: Implement** — `src/ingestion/ca_puf/read.py`

```python
"""Read CMS's California state-based exchange PUF: a zip of CSVs, into plain rows.

Pure functions, no database, so every rule here is unit-tested. Profile of the
2026 file: docs/findings/ca-sbe-puf.md. Kept: individual-market, on-exchange,
medical plans. Cost shares: in-network tier 1, individual, the only values
the search reads and the only ones whose API wording is verified.
"""
import csv
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

# The API's words (docs/findings/cms-marketplace-api.md); the search matches them exactly.
NO_CSR = "Exchange variant (no CSR)"
IN_NETWORK = "In-Network"
INDIVIDUAL = "Individual"

# (column, kind, cost_share_type). CMS spells TIER1 and TIER 1 both ways.
COST_SHARE_COLUMNS = (
    ("TEHB DED INN TIER 1 INDIVIDUAL", "deductible", "Combined Medical and Drug EHB Deductible"),
    ("MEHB DED INN TIER1 INDIVIDUAL", "deductible", "Medical EHB Deductible"),
    ("DEHB DED INN TIER1 INDIVIDUAL", "deductible", "Drug EHB Deductible"),
    ("TEHB INN TIER 1 INDIVIDUAL MOOP", "moop", "Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)"),
)
_PLAN_COLUMNS = ("BUSINESS YEAR", "STATE CODE", "ISSUER ID", "MARKET COVERAGE", "DENTAL ONLY PLAN",
                 "QHP NONQHP TYPE ID", "STANDARD COMPONENT ID", "PLAN ID", "PLAN MARKETING NAME", "PLAN TYPE",
                 "METAL LEVEL", "IS HSA ELIGIBLE", "NATIONAL NETWORK", "SERVICE AREA ID", "CSR VARIATION TYPE",
                 *(column for column, _, _ in COST_SHARE_COLUMNS))
_RATE_COLUMNS = ("PLAN ID", "RATING AREA ID", "AGE", "INDIVIDUAL RATE")
_AREA_COLUMNS = ("ISSUER ID", "SERVICE AREA ID", "COVER ENTIRE STATE", "COUNTY", "PARTIAL COUNTY", "ZIP CODE",
                 "MARKET COVERAGE", "DENTAL PLAN ONLY")

_MEMBER = re.compile(r"^CA(Plans|Rates|ServiceAreas)(\d{8})\.csv$")
_MONEY = re.compile(r"^\$?([0-9][0-9,]*(?:\.[0-9]+)?)$")
_PLAN_ID = re.compile(r"^\d{5}CA\d{7}-0[0-6]$")
_FIPS = re.compile(r"^06\d{3}$")
_ZIP = re.compile(r"^\d{5}$")
_AREA = re.compile(r"^Rating Area (\d{1,2})$")


class PufFormatError(ValueError):
    """The file is not the shape this reader was written against; nothing is loaded."""


@dataclass(frozen=True)
class PufPlan:
    hios_plan_id: str
    issuer_id: str
    marketing_name: str
    metal_level: str
    plan_type: str
    hsa_eligible: bool
    has_national_network: bool
    service_area_id: str


@dataclass(frozen=True)
class PufCostShare:
    hios_plan_id: str
    kind: str
    cost_share_type: str
    csr_variant: str
    amount: Decimal


@dataclass(frozen=True)
class PufServiceArea:
    issuer_id: str
    service_area_id: str
    countyfips: str | None  # None: the whole state
    zipcodes: tuple[str, ...] | None  # None: the whole county


@dataclass(frozen=True)
class Puf:
    label: str
    plans: tuple[PufPlan, ...]
    cost_shares: tuple[PufCostShare, ...]
    service_areas: tuple[PufServiceArea, ...]
    rates: dict[tuple[str, int, int], Decimal]  # (plan, rating area, age) -> monthly rate


def puf_money(text: str) -> Decimal | None:
    value = text.strip()
    if not value or value.lower() == "not applicable":
        return None
    match = _MONEY.match(value)
    if not match:
        raise PufFormatError(f"not an amount: {value!r}")
    return Decimal(match.group(1).replace(",", ""))


def age_key(text: str) -> int:
    if text == "0-14":
        return 14
    if text == "64 and over":
        return 64
    if text.isdigit() and 15 <= int(text) <= 63:
        return int(text)
    raise PufFormatError(f"unknown age band {text!r}")


def _yes(text: str) -> bool:
    if text not in ("Yes", "No"):
        raise PufFormatError(f"expected Yes or No, got {text!r}")
    return text == "Yes"


def _is_kept(row: dict) -> bool:
    return (row["MARKET COVERAGE"] == "Individual" and row["DENTAL ONLY PLAN"] == "No"
            and row["QHP NONQHP TYPE ID"] == "On the Exchange" and not row["PLAN ID"].endswith("-00"))


def _rows(archive: zipfile.ZipFile, name: str, required: tuple[str, ...]) -> list[dict]:
    try:
        text = archive.read(name).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PufFormatError(f"{name} is not UTF-8: {exc}") from None
    reader = csv.DictReader(io.StringIO(text))
    absent = [column for column in required if column not in (reader.fieldnames or ())]
    if absent:
        raise PufFormatError(f"{name} has no column {absent[0]!r}")
    return list(reader)


def _members(archive: zipfile.ZipFile) -> tuple[dict[str, str], str]:
    found: dict[str, tuple[str, str]] = {}
    for name in archive.namelist():
        match = _MEMBER.match(Path(name).name)
        if match:
            found[match.group(1)] = (name, match.group(2))
    missing = {"Plans", "Rates", "ServiceAreas"} - set(found)
    if missing:
        raise PufFormatError(f"the zip has no CA{', CA'.join(sorted(missing))} file")
    labels = {label for _, label in found.values()}
    if len(labels) != 1:
        raise PufFormatError(f"the files carry different dates: {sorted(labels)}")
    return {kind: name for kind, (name, _) in found.items()}, labels.pop()


def _plans(rows: list[dict], year: int) -> tuple[tuple[PufPlan, ...], tuple[PufCostShare, ...]]:
    kept = [row for row in rows if _is_kept(row)]
    for row in kept:
        if row["BUSINESS YEAR"] != str(year) or row["STATE CODE"] != "CA":
            raise PufFormatError(f"plan {row['PLAN ID']} is for plan year {row['BUSINESS YEAR']} "
                                 f"in {row['STATE CODE']}, not {year} in CA")
        if not _PLAN_ID.match(row["PLAN ID"]) or row["PLAN ID"][:14] != row["STANDARD COMPONENT ID"]:
            raise PufFormatError(f"unexpected plan id {row['PLAN ID']!r}")

    standard = {row["STANDARD COMPONENT ID"]: row for row in kept if row["PLAN ID"].endswith("-01")}
    bases = {row["STANDARD COMPONENT ID"] for row in kept}
    if missing := sorted(bases - set(standard)):
        raise PufFormatError(f"plan {missing[0]} has no -01 row")

    plans = tuple(
        PufPlan(hios_plan_id=base, issuer_id=row["ISSUER ID"], marketing_name=row["PLAN MARKETING NAME"].strip(),
                metal_level=row["METAL LEVEL"], plan_type=row["PLAN TYPE"], hsa_eligible=_yes(row["IS HSA ELIGIBLE"]),
                has_national_network=_yes(row["NATIONAL NETWORK"]), service_area_id=row["SERVICE AREA ID"])
        for base, row in sorted(standard.items())
    )

    shares: dict[tuple[str, str, str, str], PufCostShare] = {}
    for row in kept:
        base = row["STANDARD COMPONENT ID"]
        variant = NO_CSR if row["PLAN ID"].endswith("-01") else row["CSR VARIATION TYPE"]
        for column, kind, cost_share_type in COST_SHARE_COLUMNS:
            amount = puf_money(row[column])
            if amount is None:
                continue
            key = (base, kind, cost_share_type, variant)
            if key in shares:
                raise PufFormatError(f"plan {base} has two {variant!r} rows")
            shares[key] = PufCostShare(base, kind, cost_share_type, variant, amount)
    return plans, tuple(shares.values())


def _service_areas(rows: list[dict]) -> tuple[PufServiceArea, ...]:
    areas = []
    for row in rows:
        if row["MARKET COVERAGE"] != "Individual" or row["DENTAL PLAN ONLY"] != "No":
            continue
        if row["COVER ENTIRE STATE"] == "true":
            areas.append(PufServiceArea(row["ISSUER ID"], row["SERVICE AREA ID"], None, None))
            continue
        fips = row["COUNTY"].rsplit(" - ", 1)[-1].strip()
        if not _FIPS.match(fips):
            raise PufFormatError(f"service area {row['SERVICE AREA ID']}: unexpected county {row['COUNTY']!r}")
        zipcodes = None
        if row["PARTIAL COUNTY"] == "true":
            zipcodes = tuple(sorted({z.strip() for z in row["ZIP CODE"].split(",") if z.strip()}))
            if not zipcodes or not all(_ZIP.match(z) for z in zipcodes):
                raise PufFormatError(f"service area {row['SERVICE AREA ID']}: bad ZIP list for county {fips}")
        areas.append(PufServiceArea(row["ISSUER ID"], row["SERVICE AREA ID"], fips, zipcodes))
    return tuple(areas)


def _rates(rows: list[dict], plan_ids: set[str]) -> dict[tuple[str, int, int], Decimal]:
    rates: dict[tuple[str, int, int], Decimal] = {}
    for row in rows:
        if row["PLAN ID"] not in plan_ids:
            continue
        match = _AREA.match(row["RATING AREA ID"])
        if not match:
            raise PufFormatError(f"unexpected rating area {row['RATING AREA ID']!r}")
        rate = puf_money(row["INDIVIDUAL RATE"])
        if rate is None:
            raise PufFormatError(f"plan {row['PLAN ID']} has an empty rate")
        rates[(row["PLAN ID"], int(match.group(1)), age_key(row["AGE"]))] = rate
    return rates


def read_puf(path: Path, year: int) -> Puf:
    with zipfile.ZipFile(path) as archive:
        members, label = _members(archive)
        plans, cost_shares = _plans(_rows(archive, members["Plans"], _PLAN_COLUMNS), year)
        rates = _rates(_rows(archive, members["Rates"], _RATE_COLUMNS), {p.hios_plan_id for p in plans})
        areas = _service_areas(_rows(archive, members["ServiceAreas"], _AREA_COLUMNS))
    return Puf(label=label, plans=plans, cost_shares=cost_shares, service_areas=areas, rates=rates)
```

- [ ] **Step 5: Run it and check it passes**

Run: `uv run pytest tests/test_ca_puf_read.py -v`
Expected: all pass.

- [ ] **Step 6: Smoke-test against the real file,** with nothing committed:

```bash
mkdir -p data/plans/raw/ca_puf && curl -sSfL -o data/plans/raw/ca_puf/2026.zip https://www.cms.gov/files/zip/californiasbpuf2026.zip
uv run python -c "from pathlib import Path; from src.ingestion.ca_puf.read import read_puf; p=read_puf(Path('data/plans/raw/ca_puf/2026.zip'),2026); print(p.label, len(p.plans), len({x.issuer_id for x in p.plans}), len(p.cost_shares), len(p.rates))"
```

Expected: `05052026 190 11 <n> <m>`. `<n>` and `<m>` are recorded in the findings doc in Task 12.

- [ ] **Step 7: Commit.** Add a CHANGELOG bullet: "A reader for CMS's California state-based exchange PUF (`src/ingestion/ca_puf/read.py`), tested against a synthetic zip."

```bash
git add src/ingestion/ca_puf/read.py tests/ca_puf_fixtures.py tests/test_ca_puf_read.py CHANGELOG.md
git commit -m "Read California's plans, rates and service areas from the CMS PUF"
```

---

### Task 7: Load the PUF — validation, writes, CLI

**Files:**
- Create: `src/ingestion/ca_puf/load.py`
- Create: `src/ingestion/ca_puf/download.py`
- Create: `src/ingestion/ca_puf/__main__.py`
- Modify: `src/ingestion/plans.py:43-57` (`resolve_states` names the new target for CA)
- Modify: `Makefile` (`ingest-ca-plans`)
- Test: `tests/test_ca_puf_load.py`, `tests/test_ingestion_plans.py` (one assertion)

**Interfaces:**
- Consumes:
  - `read_puf`, `Puf` (Task 6)
  - `table_rows`, `area_for`, `county_area`, `LOS_ANGELES` (Task 5)
  - `issuer_name` (Task 5)
  - the models (Task 4)
  - `upsert` (`src/ingestion/plans.py:141`)
- Produces:
  - `CATALOG_SOURCE = "ca_sbe_puf"`
  - `LoadError(ValueError)`
  - `LoadReport(plans, issuers, plan_counties, dropped_unrated, rates, unrated_zips)`
  - `sold_counties(puf, counties) -> tuple[dict[str, dict[str, tuple[str, ...] | None]], int]`
  - `load(session, puf, *, year, file_url, sha256) -> LoadReport`
  - `download(year, *, refresh=False) -> Path`
  - `NotPublishedError`
  - `make ingest-ca-plans YEAR= [ZIP=] [REFRESH=1]`

- [ ] **Step 1: Write the failing test** — `tests/test_ca_puf_load.py`

```python
"""Loading a California PUF into the catalog (ADR 0024). Real Postgres, plan year 1999."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.ingestion.ca_puf.load import LoadError, load, sold_counties
from src.ingestion.ca_puf.read import read_puf
from src.ingestion.marketplace_api import County
from src.ingestion.plans import _write_zip_counties
from src.models.plan import CatalogLoad, Issuer, Plan, PlanCostShare, PlanCounty, PlanRate, RatingArea
from tests.ca_puf_fixtures import YEAR, area_row, plan_row, rate_row, write_puf

KAISER = "40513CA0010001"
WHA_NORTH = "93689CA0110001"  # rated in area 2 only
WHA_SAC = "93689CA0150001"  # rated in area 3 only
LA_16 = ("90001", "90002")
LA_15 = ("90601",)
LA_UNLISTED = ("90134",)


def _crosswalk(session):
    """Real California FIPS, 1999: Los Angeles (both areas and an unlisted prefix),
    Marin (area 2), Sacramento (area 3), a Texas county to prove it is untouched."""
    _write_zip_counties(session, [
        County("CA", "06037", "Los Angeles", LA_16 + LA_15 + LA_UNLISTED),
        County("CA", "06041", "Marin", ("94901",)),
        County("CA", "06067", "Sacramento", ("95814",)),
        County("TX", "48001", "Anderson", ("75801",)),
    ], YEAR)


def _file(tmp_path, *, plans=None, rates=None, areas=None):
    plans = plans or [
        plan_row(f"{KAISER}-01"),
        plan_row(f"{WHA_NORTH}-01", issuer="93689"),
        plan_row(f"{WHA_SAC}-01", issuer="93689"),
    ]
    rates = rates or [
        rate_row(KAISER, 16, "40", "500.00"), rate_row(KAISER, 15, "40", "480.00"),
        rate_row(WHA_NORTH, 2, "40", "450.00"), rate_row(WHA_SAC, 3, "40", "440.00"),
    ]
    areas = areas or [
        area_row("Los Angeles - 06037"),
        area_row("Marin - 06041", issuer="93689"), area_row("Sacramento - 06067", issuer="93689"),
    ]
    return read_puf(write_puf(tmp_path, plans=plans, rates=rates, areas=areas), YEAR)


def _load(session, puf):
    return load(session, puf, year=YEAR, file_url="file:test.zip", sha256="a" * 64)


def test_a_plan_is_sold_only_where_it_has_a_rate(tmp_path, session):
    """WHA files one service area over two rating areas, with a plan per area."""
    _crosswalk(session)
    sold, dropped = sold_counties(_file(tmp_path), {"06037": LA_16 + LA_15 + LA_UNLISTED,
                                                     "06041": ("94901",), "06067": ("95814",)})

    assert sold[WHA_NORTH] == {"06041": None}
    assert sold[WHA_SAC] == {"06067": None}
    assert dropped == 2
    # Rated in both Los Angeles areas: the whole county.
    assert sold[KAISER] == {"06037": None}


def test_in_los_angeles_a_plan_keeps_the_zips_of_its_rated_area_and_those_with_none(tmp_path, session):
    _crosswalk(session)
    puf = _file(tmp_path, plans=[plan_row(f"{KAISER}-01")], rates=[rate_row(KAISER, 16, "40", "500.00")],
                areas=[area_row("Los Angeles - 06037")])

    sold, _ = sold_counties(puf, {"06037": LA_16 + LA_15 + LA_UNLISTED})

    assert sold[KAISER] == {"06037": ("90001", "90002", "90134")}


def test_loading_writes_the_catalog_and_loading_again_changes_nothing(tmp_path, session):
    _crosswalk(session)
    puf = _file(tmp_path)

    first = _load(session, puf)
    counts = [session.query(model).count() for model in (Plan, PlanCounty, PlanCostShare, PlanRate, RatingArea)]
    again = _load(session, puf)

    assert (first.plans, first.issuers, first.dropped_unrated, first.unrated_zips) == (3, 2, 2, ("90134",))
    assert [session.query(model).count() for model in (Plan, PlanCounty, PlanCostShare, PlanRate, RatingArea)] == counts
    assert again == first
    kaiser = session.scalar(select(Plan).where(Plan.hios_plan_id == KAISER, Plan.plan_year == YEAR))
    assert (kaiser.catalog_source, kaiser.state, kaiser.premium_reference) == ("ca_sbe_puf", "CA", None)
    assert session.scalar(select(Issuer.name).where(Issuer.hios_issuer_id == "40513", Issuer.plan_year == YEAR)) \
        == "Kaiser Permanente"
    assert session.scalar(select(PlanRate.individual_rate).where(
        PlanRate.plan_id == kaiser.id, PlanRate.rating_area == 15, PlanRate.age == 40)) == Decimal("480.00")
    assert session.query(CatalogLoad).filter_by(plan_year=YEAR, state="CA").count() == 2


def test_a_plan_dropped_from_the_file_is_deleted_and_texas_is_untouched(tmp_path, session):
    _crosswalk(session)
    _load(session, _file(tmp_path))
    texas = Issuer(hios_issuer_id="11111", plan_year=YEAR, name="Texan", state="TX")
    session.add(texas)
    session.flush()
    session.add(Plan(issuer_id=texas.id, hios_plan_id="11111TX0010001", plan_year=YEAR, marketing_name="T",
                     metal_level="Silver", plan_type="HMO", state="TX", hsa_eligible=False,
                     has_national_network=False))
    session.flush()

    _load(session, _file(tmp_path, plans=[plan_row(f"{KAISER}-01")], rates=[rate_row(KAISER, 16, "40", "1.00")],
                         areas=[area_row("Los Angeles - 06037")]))

    left = set(session.scalars(select(Plan.hios_plan_id).where(Plan.plan_year == YEAR)))
    assert left == {KAISER, "11111TX0010001"}


@pytest.mark.parametrize("change, message", [
    ({"plans": [plan_row("12345CA0010001-01", issuer="12345")],
      "rates": [rate_row("12345CA0010001", 16, "40", "1.00")]}, "12345"),
    ({"rates": [rate_row(KAISER, 16, "40", "1.00"), rate_row(WHA_NORTH, 2, "40", "1.00")]}, "no rates"),
    ({"rates": [rate_row(KAISER, 16, "40", "1.00"), rate_row(KAISER, 19, "40", "1.00"),
                rate_row(WHA_NORTH, 2, "40", "1.00"), rate_row(WHA_SAC, 3, "40", "1.00")]}, "area 19"),
    ({"areas": [area_row("Los Angeles - 06037"), area_row("Marin - 06041", issuer="93689"),
                area_row("Orange - 06059", issuer="93689")]}, "06059"),
])
def test_a_file_that_breaks_a_rule_writes_nothing(tmp_path, session, change, message):
    _crosswalk(session)

    with pytest.raises(LoadError, match=message):
        _load(session, _file(tmp_path, **change))

    assert session.query(Plan).filter(Plan.plan_year == YEAR).count() == 0
    assert session.query(RatingArea).filter(RatingArea.plan_year == YEAR).count() == 0


def test_without_a_crosswalk_for_the_year_nothing_is_loaded(tmp_path, session):
    with pytest.raises(LoadError, match="ZIP-to-county crosswalk"):
        _load(session, _file(tmp_path))
```

The parametrized cases, in order, expect these failures:
1. **Unknown issuer:** `12345` is not in `CA_ISSUERS`.
2. **No rates:** `WHA_SAC` has none.
3. **Rated where not sold:** Kaiser is rated in area 19, San Diego, but sold only in Los Angeles.
4. **County missing from the crosswalk:** Orange isn't in the 1999 crosswalk.

- [ ] **Step 2: Run it and check it fails**

Run: `uv run pytest tests/test_ca_puf_load.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingestion.ca_puf.load'`

- [ ] **Step 3: Implement** — `src/ingestion/ca_puf/load.py`

```python
"""Write a read California PUF into the catalog: one transaction, validated first.

Every rule is checked before the first write, so a bad file changes nothing and
the previous load keeps serving. The caller owns the transaction (get_session).
"""
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, insert, select

from src.models.plan import CatalogLoad, Issuer, Plan, PlanCostShare, PlanCounty, PlanRate, RatingArea, ZipCounty

from ..plans import upsert
from .issuers import UnknownIssuerError, issuer_name
from .rating_areas import LOS_ANGELES, UnmappedCountyError, area_for, county_area, table_rows
from .read import IN_NETWORK, INDIVIDUAL, Puf

STATE = "CA"
CATALOG_SOURCE = "ca_sbe_puf"
_NOT_SOLD = object()


class LoadError(ValueError):
    """The file breaks a rule; nothing was written. The message says which."""


@dataclass(frozen=True)
class LoadReport:
    plans: int
    issuers: int
    plan_counties: int
    dropped_unrated: int
    rates: int
    unrated_zips: tuple[str, ...]


def _counties(session, year: int) -> dict[str, tuple[str, ...]]:
    rows = session.execute(
        select(ZipCounty.countyfips, ZipCounty.zipcode).where(ZipCounty.state == STATE, ZipCounty.plan_year == year)
    ).all()
    counties: dict[str, list[str]] = defaultdict(list)
    for fips, zipcode in rows:
        counties[fips].append(zipcode)
    return {fips: tuple(sorted(zips)) for fips, zips in counties.items()}


def _zips_sold(fips: str, partial: tuple[str, ...] | None, all_zips: tuple[str, ...], rated: set[int]):
    """The ZIPs of a county a plan is sold in: None for all of them, _NOT_SOLD for none."""
    if fips != LOS_ANGELES:
        return partial if county_area(fips) in rated else _NOT_SOLD
    candidates = partial or all_zips
    if not any(area_for(fips, z) in rated for z in candidates):
        return _NOT_SOLD
    # A ZIP with no rating area stays: it is sold there, just not priceable.
    kept = tuple(z for z in candidates if area_for(fips, z) is None or area_for(fips, z) in rated)
    return None if partial is None and set(kept) == set(all_zips) else kept


def _merge(current, zips):
    if current is None or zips is None:
        return None
    return tuple(sorted(set(current) | set(zips)))


def sold_counties(puf: Puf, counties: dict[str, tuple[str, ...]]):
    """Each plan's counties, and their ZIPs where it is sold in only some; and the pairs dropped.

    A plan is sold in a service-area county only where it has a rate for that
    county's rating area: Western Health Advantage files one service area over
    areas 2 and 3, with separate plans for each.
    """
    rated: dict[str, set[int]] = defaultdict(set)
    for plan_id, area, _age in puf.rates:
        rated[plan_id].add(area)
    by_area = defaultdict(list)
    for service_area in puf.service_areas:
        by_area[(service_area.issuer_id, service_area.service_area_id)].append(service_area)

    sold: dict[str, dict[str, tuple[str, ...] | None]] = {}
    dropped = 0
    for plan in puf.plans:
        areas = rated.get(plan.hios_plan_id)
        if not areas:
            raise LoadError(f"plan {plan.hios_plan_id} has no rates")
        mine: dict[str, tuple[str, ...] | None] = {}
        for service_area in by_area[(plan.issuer_id, plan.service_area_id)]:
            for fips in ([service_area.countyfips] if service_area.countyfips else sorted(counties)):
                if fips not in counties:
                    raise LoadError(f"plan {plan.hios_plan_id}: county {fips} is not in the ZIP-to-county crosswalk")
                zips = _zips_sold(fips, service_area.zipcodes, counties[fips], areas)
                if zips is _NOT_SOLD:
                    dropped += 1
                    continue
                mine[fips] = _merge(mine[fips], zips) if fips in mine else zips
        if not mine:
            raise LoadError(f"plan {plan.hios_plan_id} is sold in no county")
        where = set()
        for fips, zips in mine.items():
            where |= {area_for(fips, z) for z in (zips or counties[fips])} - {None}
        if stray := sorted(areas - where):
            raise LoadError(f"plan {plan.hios_plan_id} is rated in area {stray[0]}, where it is not sold")
        sold[plan.hios_plan_id] = mine
    return sold, dropped


def load(session, puf: Puf, *, year: int, file_url: str, sha256: str) -> LoadReport:
    counties = _counties(session, year)
    if not counties:
        raise LoadError(f"no California ZIP-to-county crosswalk for {year}: run `make ingest-plans` for that year first")
    try:
        rating_rows = table_rows(counties)
        names = {plan.issuer_id: issuer_name(plan.issuer_id) for plan in puf.plans}
    except (UnmappedCountyError, UnknownIssuerError) as exc:
        raise LoadError(str(exc)) from None
    sold, dropped = sold_counties(puf, counties)
    unrated_zips = tuple(z for z in counties.get(LOS_ANGELES, ()) if area_for(LOS_ANGELES, z) is None)

    # Validated: from here on, only writes.
    upsert(session, Issuer, [{"hios_issuer_id": issuer, "plan_year": year, "name": name, "state": STATE}
                             for issuer, name in sorted(names.items())],
           "uq_issuers_hios_issuer_id_plan_year", ("hios_issuer_id", "plan_year"))
    issuer_ids = dict(session.execute(
        select(Issuer.hios_issuer_id, Issuer.id).where(Issuer.plan_year == year, Issuer.hios_issuer_id.in_(names))
    ).all())
    upsert(session, Plan, [{
        "issuer_id": issuer_ids[plan.issuer_id], "hios_plan_id": plan.hios_plan_id, "plan_year": year,
        "marketing_name": plan.marketing_name, "metal_level": plan.metal_level, "plan_type": plan.plan_type,
        "state": STATE, "premium_reference": None, "hsa_eligible": plan.hsa_eligible,
        "has_national_network": plan.has_national_network, "catalog_source": CATALOG_SOURCE,
    } for plan in puf.plans], "uq_plans_hios_plan_id_plan_year", ("hios_plan_id", "plan_year"))

    ids = [plan.hios_plan_id for plan in puf.plans]
    # The file is authoritative: a plan it no longer lists goes, with its rows.
    session.execute(delete(Plan).where(Plan.plan_year == year, Plan.catalog_source == CATALOG_SOURCE,
                                       Plan.hios_plan_id.not_in(ids)))
    plan_ids = dict(session.execute(
        select(Plan.hios_plan_id, Plan.id).where(Plan.plan_year == year, Plan.catalog_source == CATALOG_SOURCE)
    ).all())
    for model in (PlanCounty, PlanCostShare, PlanRate):
        session.execute(delete(model).where(model.plan_id.in_(list(plan_ids.values()))))

    county_rows = [{"plan_id": plan_ids[plan_id], "countyfips": fips, "zipcodes": list(zips) if zips else None}
                   for plan_id, where in sold.items() for fips, zips in where.items()]
    share_rows = [{"plan_id": plan_ids[s.hios_plan_id], "kind": s.kind, "cost_share_type": s.cost_share_type,
                   "csr_variant": s.csr_variant, "network_tier": IN_NETWORK, "family_cost": INDIVIDUAL,
                   "amount": s.amount} for s in puf.cost_shares]
    rate_rows = [{"plan_id": plan_ids[plan_id], "rating_area": area, "age": age, "individual_rate": rate}
                 for (plan_id, area, age), rate in puf.rates.items()]
    for model, rows in ((PlanCounty, county_rows), (PlanCostShare, share_rows), (PlanRate, rate_rows)):
        if rows:
            session.execute(insert(model), rows)

    session.execute(delete(RatingArea).where(RatingArea.plan_year == year, RatingArea.state == STATE))
    session.execute(insert(RatingArea), [{"state": STATE, "plan_year": year, "countyfips": fips, "zip3": zip3,
                                          "rating_area": area} for fips, zip3, area in rating_rows])
    session.add(CatalogLoad(source=CATALOG_SOURCE, state=STATE, plan_year=year, file_url=file_url,
                            file_label=puf.label, sha256=sha256, plans=len(ids)))
    session.flush()
    return LoadReport(plans=len(ids), issuers=len(names), plan_counties=len(county_rows), dropped_unrated=dropped,
                      rates=len(rate_rows), unrated_zips=unrated_zips)
```

The test `test_a_file_that_breaks_a_rule_writes_nothing` also passes for the missing-county case: `sold_counties` raises before the first write.

`src/ingestion/ca_puf/download.py`:

```python
"""Fetch the California PUF from CMS, once per plan year, into data/plans/raw/ca_puf/."""
import hashlib
from pathlib import Path

import requests

from ..constants import PLANS_RAW, USER_AGENT

PUF_URL = "https://www.cms.gov/files/zip/californiasbpuf{year}.zip"
CACHE = PLANS_RAW / "ca_puf"


class NotPublishedError(Exception):
    """CMS has not published this year's file (it does so May to August of the plan year)."""


def download(year: int, *, refresh: bool = False, cache: Path = CACHE) -> Path:
    path = cache / f"{year}.zip"
    if path.exists() and not refresh:
        return path
    response = requests.get(PUF_URL.format(year=year), headers={"User-Agent": USER_AGENT}, timeout=(10, 120))
    if response.status_code == 404:
        raise NotPublishedError(f"CMS has not published the {year} California PUF yet")
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise ValueError(f"{PUF_URL.format(year=year)} did not return a zip")
    cache.mkdir(parents=True, exist_ok=True)
    # Written aside and renamed: a killed run leaves the old file or none.
    partial = path.with_suffix(".tmp")
    partial.write_bytes(response.content)
    partial.replace(path)
    return path


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

`src/ingestion/ca_puf/__main__.py`:

```python
"""`make ingest-ca-plans YEAR=2026 [ZIP=path] [REFRESH=1]`: load California's plans from the CMS PUF."""
import argparse
import sys
from pathlib import Path

import requests

from src.core.db import get_session
from src.core.exceptions import MarketplaceApiKeyMissingError
from src.core.logging import get_logger, setup_logging
from src.ingestion.sources.registry import SourceNotApprovedError, require_enabled
from src.models.plan import ZipCounty

from ..marketplace_api import county_zips
from ..plans import _write_zip_counties
from .download import PUF_URL, NotPublishedError, download, sha256_of
from .load import STATE, LoadError, load
from .read import PufFormatError, read_puf

logger = get_logger(__name__)


def parse_args(args):
    parser = argparse.ArgumentParser(description="Load California's Covered California plans from the CMS PUF.")
    parser.add_argument("--year", type=int, required=True, help="Plan year, e.g. 2026")
    parser.add_argument("--zip", help="A PUF zip downloaded by hand, instead of fetching it")
    parser.add_argument("--refresh", action="store_true", help="Download again even if a copy is kept")
    return parser.parse_args(args)


def _ensure_crosswalk(year: int) -> None:
    with get_session() as session:
        if session.query(ZipCounty).filter_by(state=STATE, plan_year=year).first():
            return
    print(f"No ZIP-to-county crosswalk for {year}; fetching CMS's (needs CMS_MARKETPLACE_API_KEY).")
    crosswalk = county_zips(year)
    with get_session() as session:
        print(f"{_write_zip_counties(session, crosswalk, year)} ZIP-to-county pairs recorded for {year}")


def main(args=sys.argv[1:]):
    parsed = parse_args(args)
    try:
        require_enabled("cms_ca_sbe_puf")
        path = Path(parsed.zip) if parsed.zip else download(parsed.year, refresh=parsed.refresh)
        puf = read_puf(path, parsed.year)
        _ensure_crosswalk(parsed.year)
        with get_session() as session:
            report = load(session, puf, year=parsed.year, sha256=sha256_of(path),
                          file_url=f"file:{path.name}" if parsed.zip else PUF_URL.format(year=parsed.year))
    except NotPublishedError as exc:
        print(exc)
        sys.exit(3)
    except (SourceNotApprovedError, PufFormatError, LoadError, MarketplaceApiKeyMissingError,
            requests.RequestException) as exc:
        sys.exit(f"California plans not loaded: {exc}")

    print(f"{report.plans} plans from {report.issuers} issuers, file {puf.label}: {report.plan_counties} "
          f"plan-county rows ({report.dropped_unrated} dropped: no rate there), {report.rates} rates")
    if report.unrated_zips:
        print(f"Los Angeles ZIPs with no CMS rating area, shown unpriced: {', '.join(report.unrated_zips)}")
    logger.info("california plans loaded: %s", report)


if __name__ == "__main__":
    setup_logging()
    main()
```

`src/ingestion/plans.py`, in `resolve_states`: replace the `raise ValueError(...)` for unknown states with:

```python
        hint = " — California is loaded by `make ingest-ca-plans`" if "CA" in unknown else ""
        raise ValueError(
            f"not HealthCare.gov marketplace states: {', '.join(unknown)} "
            f"(they run their own exchange, or are not state codes){hint}"
        )
```

In `Makefile`, add `ingest-ca-plans` to `.PHONY`, and after `ingest-plans` add:

```make
# California's plans, from CMS's state-based exchange PUF (ADR 0024). YEAR is
# required: the file for a plan year appears May to August of that year.
# ZIP=path loads a file downloaded by hand; REFRESH=1 downloads it again.
ingest-ca-plans:
	@test -n "$(YEAR)" || { echo "YEAR is required, e.g. make ingest-ca-plans YEAR=2026"; exit 2; }
	uv run python -m src.ingestion.ca_puf --year $(YEAR) $(if $(ZIP),--zip $(ZIP)) $(if $(REFRESH),--refresh)
```

Append to `tests/test_ingestion_plans.py`:

```python
def test_asking_the_api_loader_for_california_names_its_own_loader():
    with pytest.raises(ValueError, match="make ingest-ca-plans"):
        resolve_states("TX,CA")
```

Import `pytest` there if it isn't already.

- [ ] **Step 4: Run it and check it passes**

Run: `uv run pytest tests/test_ca_puf_load.py tests/test_ingestion_plans.py -v`
Expected: all pass.

- [ ] **Step 5: Load the real 2026 file.** Local only; nothing from `data/` is committed.

Run: `make ingest-ca-plans YEAR=2026 ZIP=data/plans/raw/ca_puf/2026.zip`

Expected, taken from the checks done in planning:

```
190 plans from 11 issuers, file 05052026: 1199 plan-county rows (40 dropped: no rate there), <n> rates
Los Angeles ZIPs with no CMS rating area, shown unpriced: 90134, 90140, 90189, 93063
```

Also run in psql (`docker compose exec db psql -U <user> <db>`):

```sql
SELECT count(*) FROM plans WHERE catalog_source='ca_sbe_puf' AND plan_year=2026;   -- 190
SELECT count(DISTINCT issuer_id) FROM plans WHERE catalog_source='ca_sbe_puf';      -- 11
SELECT count(*) FROM plan_counties pc JOIN plans p ON p.id=pc.plan_id
  WHERE p.catalog_source='ca_sbe_puf' AND NOT EXISTS (
    SELECT 1 FROM plan_rates r WHERE r.plan_id=p.id);                              -- 0
```

Stop and report if any number differs.

- [ ] **Step 6: Commit.** Add a CHANGELOG bullet: "`make ingest-ca-plans YEAR=`: loads Covered California's plans from CMS's PUF in one validated transaction. A plan is sold only where it has a filed rate, and a file that breaks a rule writes nothing."

```bash
git add src/ingestion/ca_puf/ src/ingestion/plans.py Makefile tests/test_ca_puf_load.py tests/test_ingestion_plans.py CHANGELOG.md
git commit -m "Load California's plans from the CMS PUF, validated before any write"
```

---

### Task 8: Plan search for a filed-rate state

**Files:**
- Modify: `src/services/plan_search.py`
- Modify: `src/core/marketplace_api.py:85-93` (guard)
- Test: `tests/test_plan_search.py`, `tests/test_marketplace_api.py`

**Interfaces:**
- Consumes:
  - `FILED_RATE_STATES` (Task 1)
  - `plan_year_on_sale` (Task 1)
  - `RatingArea` and `PlanRate` (Task 4)
- Produces:
  - `PlanSearchResult` gains `premium_source: Literal["cms_live", "cms_filed_rates"] | None = None`, `plan_year_on_sale: int | None = None` and `prior_year: bool = False`
  - `rate_age(age: int) -> int`
  - `resolve_place(session, zip_code, county_fips) -> tuple[int, CountyOption] | PlanSearchResult`
  - `find_plans(..., zip_code: str | None = None, filed_rate: tuple[int | None, int] | None = None)`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_plan_search.py`

```python
from datetime import date

from src.models.plan import Issuer, Plan, PlanCounty, PlanRate, RatingArea, ZipCounty
from src.services.plan_search import rate_age

CA_COUNTY = "99101"  # fake FIPS: keeps a locally loaded 2026 California catalog out


def _ca_catalog(session, *, zipcodes=None):
    """A made-up California county: ZIP 00101 prices in area 16, 00601 in 15, 00934 in none.
    Plan K (Kaiser-like) is rated in both areas; plan P only where zipcodes allow."""
    session.add_all([ZipCounty(zipcode=z, plan_year=YEAR, countyfips=CA_COUNTY, county_name="Angeles", state="CA")
                     for z in ("00101", "00601", "00934")])
    session.add_all([RatingArea(state="CA", plan_year=YEAR, countyfips=CA_COUNTY, zip3="001", rating_area=16),
                     RatingArea(state="CA", plan_year=YEAR, countyfips=CA_COUNTY, zip3="006", rating_area=15)])
    issuer = Issuer(hios_issuer_id="99999", plan_year=YEAR, name="Kaiser Permanente", state="CA")
    session.add(issuer)
    session.flush()
    plans = {}
    for plan_id, metal, zips in (("99999CA0010001", "Silver", None), ("99999CA0010002", "Expanded Bronze", zipcodes)):
        plan = Plan(issuer_id=issuer.id, hios_plan_id=plan_id, plan_year=YEAR, marketing_name=f"Plan {plan_id[-1]}",
                    metal_level=metal, plan_type="HMO", state="CA", hsa_eligible=False, has_national_network=False,
                    catalog_source="ca_sbe_puf")
        session.add(plan)
        session.flush()
        session.add(PlanCounty(plan_id=plan.id, countyfips=CA_COUNTY, zipcodes=zips))
        for area, base in ((16, 500), (15, 480)):
            session.add_all([PlanRate(plan_id=plan.id, rating_area=area, age=age,
                                      individual_rate=Decimal(base + age - (100 if metal != "Silver" else 0)))
                             for age in (14, 40, 64)])
        plans[plan_id] = plan
    session.flush()
    return plans


def _ca_search(session, zip_code="00101", age=40, on=date(2026, 9, 24), **kwargs):
    with patch("src.services.plan_search.age_rated_premiums") as cms, \
         patch("src.services.plan_search._today", return_value=on):
        return search_plans(session, zip_code=zip_code, age=age, **kwargs), cms


def test_california_is_priced_from_filed_rates_never_from_cms_live(session):
    _ca_catalog(session)

    result, cms = _ca_search(session)

    cms.assert_not_called()
    assert result.status == "ok"
    assert result.premium_source == "cms_filed_rates"
    assert [(p.hios_plan_id, p.monthly_premium) for p in result.plans] == [
        ("99999CA0010002", Decimal("440")), ("99999CA0010001", Decimal("540"))]
    assert {(p.premium_age, p.county_name, p.state) for p in result.plans} == {(40, "Angeles", "CA")}


def test_los_angeles_prices_each_zip_in_its_own_area(session):
    _ca_catalog(session)

    area_15, _ = _ca_search(session, zip_code="00601")

    assert [p.monthly_premium for p in area_15.plans] == [Decimal("420"), Decimal("520")]


def test_a_zip_with_no_rating_area_is_shown_unpriced_never_guessed(session):
    _ca_catalog(session)

    result, cms = _ca_search(session, zip_code="00934")

    cms.assert_not_called()
    assert result.status == "ok"
    assert all(p.monthly_premium is None and p.premium_age is None for p in result.plans)


def test_ages_outside_the_filed_bands_use_the_nearest_band(session):
    _ca_catalog(session)

    child, _ = _ca_search(session, age=10)
    older, _ = _ca_search(session, age=70)

    assert rate_age(10) == 14 and rate_age(70) == 64 and rate_age(40) == 40
    assert child.plans[0].monthly_premium == Decimal("414")
    assert older.plans[0].monthly_premium == Decimal("464")
    assert child.plans[0].premium_age == 10


def test_a_plan_sold_in_part_of_a_county_is_listed_only_for_its_zips(session):
    _ca_catalog(session, zipcodes=["00601"])

    inside, _ = _ca_search(session, zip_code="00601")
    outside, _ = _ca_search(session, zip_code="00101")

    assert "99999CA0010002" in [p.hios_plan_id for p in inside.plans]
    assert [p.hios_plan_id for p in outside.plans] == ["99999CA0010001"]


def test_in_open_enrollment_last_years_california_data_is_marked_prior_year(session):
    _ca_catalog(session)

    before, _ = _ca_search(session, on=date(1999, 10, 31))
    during, _ = _ca_search(session, on=date(1999, 11, 15))

    assert (before.prior_year, before.plan_year_on_sale) == (False, 1999)
    assert (during.prior_year, during.plan_year_on_sale) == (True, 2000)
    assert during.status == "ok" and during.plan_year == YEAR


def test_a_california_zip_before_any_california_load_names_its_exchange_state(session):
    _catalog(session)  # some plans exist, none in California; it rewrites the year's crosswalk, so first
    session.add(ZipCounty(zipcode="00199", plan_year=YEAR, countyfips="99199", county_name="Nowhere", state="CA"))
    session.flush()

    result, cms = _ca_search(session, zip_code="00199")

    assert (result.status, result.state) == ("not_marketplace_state", "CA")
    cms.assert_not_called()


def test_the_api_path_is_unchanged_and_says_it_is_live(session):
    _catalog(session)
    result, cms = _search(session, live={"11111TX0010001": Decimal("400.00")})

    cms.assert_called_once()
    assert (result.premium_source, result.prior_year) == ("cms_live", False)
```

Append to `tests/test_marketplace_api.py`:

```python
def test_a_state_the_api_does_not_serve_is_refused_before_any_request():
    with patch("src.core.marketplace_api.request") as request:
        with pytest.raises(ValueError, match="CA is not served"):
            age_rated_premiums(["40513CA0010001"], age=40, state="CA", countyfips="06037", zipcode="90012", year=2026)
    request.assert_not_called()
```

Add `age_rated_premiums` to that file's imports from `src.core.marketplace_api`, along with `patch` and `pytest` if they're missing.

- [ ] **Step 2: Run them and check they fail**

Run: `uv run pytest tests/test_plan_search.py tests/test_marketplace_api.py -v -k "california or zip or ages or prior or api_path or not_served"`
Expected: FAIL with `ImportError: cannot import name 'rate_age'`

- [ ] **Step 3: Implement**

In `src/core/marketplace_api.py`, make the first statement in `age_rated_premiums`, after the docstring:

```python
    if state not in MARKETPLACE_STATES:
        # A filed-rate state is priced from plan_rates; asking CMS would bill a request for zeros.
        raise ValueError(f"{state} is not served by the Marketplace API")
```

In `src/services/plan_search.py`:

1. **Imports.** Add `from datetime import UTC, date, datetime`, change the sqlalchemy import to `from sqlalchemy import and_, exists, func, null, or_, select, true`, and add:

```python
from src.core.exchanges import FILED_RATE_STATES
from src.core.plan_year import plan_year_on_sale
from src.models.plan import Issuer, Plan, PlanCostShare, PlanCounty, PlanRate, RatingArea, ZipCounty
```

replacing the existing `src.models.plan` import line.

2. **Module docstring.** Append to it: "In a filed-rate state (California) the premium is the filed rate for the plan, rating area and age, read here in SQL; CMS is never called (ADR 0024)."

3. **Constants and helpers,** after `_BRONZE_LEVELS`:

```python
# The filed rate tables' age bands: 0-14 are one rate, as are 64 and over.
_YOUNGEST_RATE_AGE = 14
_OLDEST_RATE_AGE = 64


def rate_age(age: int) -> int:
    return min(max(age, _YOUNGEST_RATE_AGE), _OLDEST_RATE_AGE)


def _today() -> date:
    return datetime.now(UTC).date()
```

4. **`PlanSearchResult`** gets three fields after `catastrophic_excluded`:

```python
    # cms_live: priced now by the API; cms_filed_rates: CMS's published rates (ADR 0024).
    premium_source: Literal["cms_live", "cms_filed_rates"] | None = None
    plan_year_on_sale: int | None = None
    # A filed-rate state's plans are from a year no longer on sale (the PUF lags).
    prior_year: bool = False
```

5. **`find_plans` signature** becomes `find_plans(session, *, countyfips: str, year: int, filters: PlanFilters, limit: int, zip_code: str | None = None, filed_rate: tuple[int | None, int] | None = None)`. Replace its body up to `base = (` with:

```python
    shares = _cost_shares()
    deductible = func.coalesce(shares.c.combined, shares.c.medical)
    in_zip = or_(PlanCounty.zipcodes.is_(None), PlanCounty.zipcodes.any(zip_code)) if zip_code else true()

    conditions = [
        Plan.plan_year == year,
        Plan.id.in_(select(PlanCounty.plan_id).where(PlanCounty.countyfips == countyfips, in_zip)),
    ]
    if filters.metal_level == "Bronze":
        conditions.append(Plan.metal_level.in_(_BRONZE_LEVELS))
    elif filters.metal_level:
        conditions.append(Plan.metal_level == filters.metal_level)
    if filters.plan_type:
        conditions.append(Plan.plan_type == filters.plan_type)
    if not filters.include_catastrophic:
        conditions.append(Plan.metal_level != _CATASTROPHIC)
    if filters.max_deductible is not None:
        conditions.append(deductible <= filters.max_deductible)

    # A filed rate is the premium; with no rating area for the ZIP, there is none.
    rates = None
    premium = null()
    if filed_rate and filed_rate[0] is not None:
        area, age = filed_rate
        rates = (select(PlanRate.plan_id, PlanRate.individual_rate)
                 .where(PlanRate.rating_area == area, PlanRate.age == age).subquery())
        premium = rates.c.individual_rate
```

   Then change `base = (select(Plan, Issuer.name.label(...), deductible.label("deductible"), ...))` to add `premium.label("filed_premium")` after `deductible.label("deductible")`. Right after the `base = (...)` statement, add:

```python
    if rates is not None:
        base = base.outerjoin(rates, rates.c.plan_id == Plan.id)
```

   The ordering becomes:

```python
    by_premium = premium.asc().nulls_last() if filed_rate else Plan.premium_reference.asc().nulls_last()
    if filters.sort_by == "deductible":
        order = (deductible.asc().nulls_last(), by_premium)
    else:
        order = (by_premium,)
```

   In the list comprehension, unpack `for plan, issuer_name, ded, filed, drug, moop, sbc_status in rows`, and set `monthly_premium=filed`.

6. **`resolve_place`,** extracted from `search_plans`. Add above `search_plans`:

```python
def _filed_rate_loaded(session, state: str, year: int) -> bool:
    return bool(session.scalar(select(exists().where(Plan.state == state, Plan.plan_year == year))))


def resolve_place(session, zip_code: str, county_fips: str | None) -> tuple[int, CountyOption] | PlanSearchResult:
    """The plan year and county a search runs in, or the result that ends it there."""
    year, counties = _counties_for_zip(session, zip_code)
    if not counties:
        return PlanSearchResult("zip_not_found")

    # 126 ZIPs cross a state line, so a ZIP can be partly in a served state.
    served = [c for c in counties if c.state in MARKETPLACE_STATES
              or (c.state in FILED_RATE_STATES and _filed_rate_loaded(session, c.state, year))]
    if not served:
        return PlanSearchResult("not_marketplace_state", state=counties[0].state)

    chosen = next((c for c in served if c.fips == county_fips), None)
    if chosen is None:
        if len(served) > 1:
            # Plans and prices differ by county; merging them would list plans
            # the user cannot buy. The model is told to ask which one.
            return PlanSearchResult("ambiguous_county", counties=tuple(served), plan_year=year)
        chosen = served[0]

    loaded = session.scalar(
        select(exists().where(PlanCounty.countyfips == chosen.fips, PlanCounty.plan_id == Plan.id,
                              Plan.plan_year == year))
    )
    if not loaded:
        return PlanSearchResult("county_not_loaded", county=chosen, plan_year=year)
    return year, chosen


def _rating_area(session, year: int, countyfips: str, zip_code: str) -> int | None:
    """The ZIP prefix's area, else the whole county's; None where CMS lists neither."""
    return session.scalar(
        select(RatingArea.rating_area)
        .where(RatingArea.plan_year == year, RatingArea.countyfips == countyfips,
               RatingArea.zip3.in_((zip_code[:3], "")))
        .order_by(RatingArea.zip3.desc())
        .limit(1)
    )
```

7. **`search_plans` body** becomes:

```python
def search_plans(session, *, zip_code: str, age: int, county_fips: str | None = None,
                 filters: PlanFilters | None = None) -> PlanSearchResult:
    filters = filters or PlanFilters()
    place = resolve_place(session, zip_code, county_fips)
    if isinstance(place, PlanSearchResult):
        return place
    year, chosen = place

    excluded = filters.metal_level is None and age > _CATASTROPHIC_MAX_AGE
    if excluded:
        filters = replace(filters, include_catastrophic=False)

    filed = chosen.state in FILED_RATE_STATES
    on_sale = plan_year_on_sale(_today())
    freshness = {"premium_source": "cms_filed_rates" if filed else "cms_live", "plan_year_on_sale": on_sale,
                 "prior_year": filed and year < on_sale}
    filed_rate = (_rating_area(session, year, chosen.fips, zip_code), rate_age(age)) if filed else None

    candidates, total = find_plans(session, countyfips=chosen.fips, year=year, filters=filters,
                                   limit=MAX_PREMIUM_BATCH, zip_code=zip_code, filed_rate=filed_rate)
    if not candidates:
        return PlanSearchResult("no_match", county=chosen, plan_year=year, catastrophic_excluded=excluded,
                                **freshness)

    if filed:
        # Already priced and ordered in SQL; say whose premium and where, as _price does.
        priced = [replace(p, county_name=chosen.name, state=chosen.state,
                          premium_age=age if p.monthly_premium is not None else None) for p in candidates]
    else:
        priced = _price(candidates, age=age, county=chosen, zip_code=zip_code, year=year)
        if filters.sort_by == "premium":
            # Live-priced plans by their real premium; any CMS did not price keep
            # their catalog order after them. sorted() is stable.
            priced = sorted(priced, key=lambda p: (not p.premium_is_live, p.monthly_premium or 0))

    shown = tuple(priced[:SHOWN_PLANS])
    logger.info("plan search: %d of %d plans shown, %d priced", len(shown), total,
                sum(p.premium_is_live for p in shown))
    return PlanSearchResult("ok", plans=shown, total_matching=total, plan_year=year, county=chosen,
                            catastrophic_excluded=excluded, **freshness)
```

Two notes:
- `PlanResult.state` is set for CA plans by `replace` above. `find_plans` already sets `state=plan.state`, so the `replace` only adds the county name.
- The `premium_is_live` property stays as it is: it means "has a premium". Task 9 tells the model which kind it is.

- [ ] **Step 4: Run it, with the whole plan-search, tools and chat suites, and check they pass**

Run: `uv run pytest tests/test_plan_search.py tests/test_marketplace_api.py tests/test_tools.py tests/test_chat.py -v`
Expected: all pass. The earlier Texas tests still pass unchanged: this is Review Focus 1–4, and the Texas path is untouched.

- [ ] **Step 5: Commit.** Add CHANGELOG bullets:
  - "California plan search: premiums are CMS's filed rates for the plan, rating area and age, read in SQL. Los Angeles prices by ZIP prefix; a ZIP with no CMS rating area shows unpriced, never guessed."
  - "Partial-county service areas list a plan only for its ZIPs."
  - "Results say when the data is from a plan year no longer on sale."

```bash
git add src/services/plan_search.py src/core/marketplace_api.py tests/test_plan_search.py tests/test_marketplace_api.py CHANGELOG.md
git commit -m "Price California plans from filed rates, by rating area and age"
```

---

### Task 9: Tell the model what a filed-rate result means

**Files:**
- Modify: `src/services/tools.py` (`_render`)
- Modify: `src/services/generation.py` (`PLAN_TOOL_PROMPT`)
- Test: `tests/test_tools.py`, `tests/test_generation.py`

**Interfaces:**
- Consumes: `PlanSearchResult.premium_source`, `.prior_year` and `.plan_year_on_sale` (Task 8), and `_exchange` (Task 3).
- Produces: `ok` and `no_match` payloads carry `premium_source`. Filed-rate payloads also carry `prior_year` and `plan_year_on_sale`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
def test_a_filed_rate_result_says_so_and_flags_a_year_no_longer_on_sale():
    result = PlanSearchResult(
        "ok", total_matching=1, plan_year=2026, county=CountyOption("06037", "Los Angeles", "CA"),
        plans=(replace(_result_plan("40513CA0010001", live=True), premium_reference=None),),
        premium_source="cms_filed_rates", plan_year_on_sale=2027, prior_year=True,
    )
    with patch("src.services.tools.search_plans", return_value=result), patch("src.services.tools.get_session"):
        payload = json.loads(run_tool("search_plans", _args(zip_code="90012", age=40)).content)

    assert (payload["premium_source"], payload["prior_year"], payload["plan_year_on_sale"]) == (
        "cms_filed_rates", True, 2027)
    assert payload["exchange"]["name"] == "Covered California"
    assert "reference_premium_age_27" not in payload["plans"][0]
    assert "90012" not in json.dumps(payload)


def test_a_live_result_carries_no_year_flags():
    result = PlanSearchResult(
        "ok", total_matching=1, plan_year=2026, county=CountyOption("48001", "Anderson", "TX"),
        plans=(_result_plan("11111TX0010001", live=True),), premium_source="cms_live", plan_year_on_sale=2026,
    )
    with patch("src.services.tools.search_plans", return_value=result), patch("src.services.tools.get_session"):
        payload = json.loads(run_tool("search_plans", _args(zip_code="75801", age=34)).content)

    assert payload["premium_source"] == "cms_live"
    assert "prior_year" not in payload
```

Add `from dataclasses import replace` to the imports.

Append to `tests/test_generation.py`:

```python
def test_the_prompt_explains_filed_rates_and_a_prior_plan_year():
    from src.services.generation import PLAN_TOOL_PROMPT

    assert "cms_filed_rates" in PLAN_TOOL_PROMPT
    assert "prior_year" in PLAN_TOOL_PROMPT
    assert "plan_year_on_sale" in PLAN_TOOL_PROMPT
```

- [ ] **Step 2: Run them and check they fail**

Run: `uv run pytest tests/test_tools.py tests/test_generation.py -v -k "filed or live_result or prior"`
Expected: 3 FAIL (`KeyError: 'premium_source'`, and assertion errors on the prompt).

- [ ] **Step 3: Implement**

In `tools._render`, add a helper above it:

```python
def _freshness(result: PlanSearchResult) -> dict:
    """How the premiums were priced, and, for filed rates, whether the year is still on sale."""
    if result.premium_source is None:
        return {}
    fields = {"premium_source": result.premium_source}
    if result.premium_source == "cms_filed_rates":
        fields |= {"prior_year": result.prior_year, "plan_year_on_sale": result.plan_year_on_sale}
    return fields
```

- In the `ok` payload, add `**_freshness(result),` after `**_exchange(...)`.
- In the generic non-ok branch (`if result.status != "ok":`), pass `**_freshness(result)` and `**_exchange(result.county.state if result.county else None)` into `_outcome`, so `no_match` in a prior year still says so.

In `generation.PLAN_TOOL_PROMPT`, insert this text right after the sentence ending `"...gives the price they would pay."`:

```python
    "When premium_source is cms_filed_rates, monthly_premium is CMS's published "
    "rate for that plan year and the searched age, before any federal tax "
    "credit or state premium help: say so. If prior_year is true, begin with: "
    "these are <plan_year> plans and prices, <plan_year_on_sale> plans aren't "
    "available here yet, and the exchange named in the result has them. "
```

- [ ] **Step 4: Run it and check it passes**

Run: `uv run pytest tests/test_tools.py tests/test_generation.py -v`
Expected: all pass.

- [ ] **Step 5: Commit.** Add a CHANGELOG bullet: "The plan tool tells the model when premiums are filed rates and when the plan year is no longer on sale, so answers lead with the year and point to Covered California."

```bash
git add src/services/tools.py src/services/generation.py tests/test_tools.py tests/test_generation.py CHANGELOG.md
git commit -m "Tell the model when premiums are filed rates for a year no longer on sale"
```

---

### Task 10: Profile says plan comparison is available in California

**Files:**
- Modify: `src/services/profile.py` (`is_marketplace_state` becomes `plan_search_available`)
- Modify: `src/api/routes/profile.py` (use the new name)
- Modify: `src/schemas/profile.py` (field comment)
- Modify: `tests/helpers.py` (seed a CA ZIP)
- Test: `tests/test_profile_api.py`, `tests/test_rate_limits.py` (run it; no change expected)

**Interfaces:**
- Consumes: `CATALOG_STATES` (Task 1).
- Produces: `plan_search_available(state: str | None) -> bool`. `marketplace_state` in both responses is true for CA.

- [ ] **Step 1: Write the failing test**

In `tests/helpers.py`, append to `ZIP_COUNTIES`:

```python
    ("00007", "99007", "Delta", "CA"),
```

Append to `tests/test_profile_api.py`:

```python
def test_a_california_zip_can_compare_plans_and_a_new_york_one_cannot(client):
    headers = _headers(client, zip_code="00007")

    assert client.get("/api/profile", headers=headers).get_json()["marketplace_state"] is True
    assert client.get("/api/counties?zip=00007").get_json()["marketplace_state"] is True
    assert client.get("/api/counties?zip=00009").get_json()["marketplace_state"] is False
```

- [ ] **Step 2: Run it and check it fails**

Run: `uv run pytest tests/test_profile_api.py -v -k california`
Expected: FAIL, `assert False is True`.

- [ ] **Step 3: Implement**

In `src/services/profile.py`:
- replace `from src.core.marketplace_api import MARKETPLACE_STATES` with `from src.core.exchanges import CATALOG_STATES`;
- replace the function with:

```python
def plan_search_available(state: str | None) -> bool:
    """Whether plan comparison has plans for the state: HealthCare.gov's, or a filed-rate state's."""
    return state in CATALOG_STATES
```

In `src/api/routes/profile.py`, rename the import and both uses: `is_marketplace_state` becomes `plan_search_available`.

In `src/schemas/profile.py`, change the `ProfileResponse.marketplace_state` comment to:

```python
    # Whether plan comparison is available: a HealthCare.gov state or a filed-rate
    # one (California). The name predates California and is kept for the frontend.
```

- [ ] **Step 4: Run the profile, rate-limit and auth suites and check they pass**

Run: `uv run pytest tests/test_profile_api.py tests/test_rate_limits.py tests/test_auth_api.py -v`
Expected: all pass. The 429 limits on `/api/profile` (60 and 10 per minute) and `/api/counties` (30 per minute) are unchanged and re-asserted by `test_rate_limits.py`.

- [ ] **Step 5: Commit.** Add a CHANGELOG bullet: "Profiles with a California ZIP now show plan comparison as available."

```bash
git add src/services/profile.py src/api/routes/profile.py src/schemas/profile.py tests/helpers.py tests/test_profile_api.py CHANGELOG.md
git commit -m "Offer plan comparison to California profiles"
```

---

### Task 11: Frontend — the right exchange, the plan year, "Not available" ratings

**Files:**
- Create: `frontend/src/features/plans/exchanges.js`
- Create: `frontend/src/features/plans/exchanges.test.js`
- Modify: `frontend/src/features/plans/PlanComparison.jsx`
- Modify: `frontend/src/features/plans/PlanComparison.test.jsx`
- Modify: `frontend/src/features/profile/ProfileFields.jsx`
- Modify: `frontend/src/features/profile/ProfileFields.test.jsx`

**Interfaces:**
- Produces: `exchangeFor(state) -> { name, url, filedRates }`

- [ ] **Step 1: Write the failing tests**

`frontend/src/features/plans/exchanges.test.js`:

```js
import { describe, expect, it } from "vitest";
import { exchangeFor } from "./exchanges";

describe("exchangeFor", () => {
  it("sends California to Covered California, priced from filed rates", () => {
    expect(exchangeFor("CA")).toEqual({
      name: "Covered California",
      url: "https://www.coveredca.com/",
      filedRates: true,
    });
  });

  it("sends every other state with plans to HealthCare.gov", () => {
    expect(exchangeFor("TX")).toEqual({
      name: "HealthCare.gov",
      url: "https://www.healthcare.gov/see-plans/",
      filedRates: false,
    });
  });
});
```

Update `frontend/src/features/plans/PlanComparison.test.jsx`:
- In the first test, change the expected table name to `"2026 Silver plans · Anderson County, TX · shown Sep 18, 2026"`. Update any other caption expectation the same way: the plan year leads, e.g. `"2026 plans · …"` for mixed levels.
- Append:

```js
  it("names Covered California and filed rates for California plans", () => {
    render(
      <PlanComparison
        plans={[plan({ state: "CA", county_name: "Los Angeles", quality_rating: null, premium_reference: null })]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(screen.getByRole("table", { name: /^2026 Silver plans · Los Angeles County, CA/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Covered California/ })).toHaveAttribute(
      "href",
      "https://www.coveredca.com/",
    );
    expect(screen.getByText(/CMS's published 2026 rates/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /HealthCare\.gov/ })).not.toBeInTheDocument();
    expect(rowFor("CHRISTUS Value Silver 70")).toHaveTextContent("Not available");
  });

  it("keeps HealthCare.gov and 'Not rated' for other states", () => {
    render(<PlanComparison plans={[plan({ quality_rating: null })]} shownAt={SHOWN_AT} />);

    expect(screen.getByRole("link", { name: /HealthCare\.gov/ })).toHaveAttribute(
      "href",
      "https://www.healthcare.gov/see-plans/",
    );
    expect(rowFor("CHRISTUS Value Silver 70")).toHaveTextContent("Not rated");
  });

  it("says a California plan with no filed rate for the ZIP is unpriced, not live-unavailable", () => {
    render(
      <PlanComparison
        plans={[plan({ state: "CA", monthly_premium: null, premium_age: null, premium_reference: null })]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(rowFor("CHRISTUS Value Silver 70")).toHaveTextContent("No filed rate for this ZIP code");
  });
```

Append to `frontend/src/features/profile/ProfileFields.test.jsx`, inside its `describe`:

```js
  it("names Covered California for a California county", () => {
    renderFields({ counties: [{ county_fips: "06037", county_name: "Los Angeles", state: "CA" }], marketplaceState: true });

    expect(screen.getByText(/sold on Covered California/)).toBeInTheDocument();
    expect(screen.queryByText(/runs its own health insurance exchange/)).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run them and check they fail**

Run: `make ui-test`
Expected: the new tests FAIL (the module is missing, and the text isn't found).

- [ ] **Step 3: Implement**

`frontend/src/features/plans/exchanges.js`:

```js
// The exchange that sells a state's plans. Mirrors src/core/exchanges.py; a
// test on each side pins California to Covered California (ADR 0024).
const HEALTHCARE_GOV = { name: "HealthCare.gov", url: "https://www.healthcare.gov/see-plans/", filedRates: false };

const OWN_EXCHANGES = {
  CA: { name: "Covered California", url: "https://www.coveredca.com/", filedRates: true },
};

export function exchangeFor(state) {
  return OWN_EXCHANGES[state] ?? HEALTHCARE_GOV;
}
```

`frontend/src/features/plans/PlanComparison.jsx`:
- remove the `HEALTHCARE_GOV` constant;
- add `import { exchangeFor } from "./exchanges";`;
- make these changes:

```jsx
function caption(plans, shownAt) {
  const levels = new Set(plans.map((p) => p.metal_level));
  const years = new Set(plans.map((p) => p.plan_year));
  const places = new Set(plans.map((p) => `${p.county_name} County, ${p.state}`));
  const shown = new Date(shownAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const noun = levels.size === 1 ? `${[...levels][0]} plans` : "plans";
  return [
    years.size === 1 ? `${[...years][0]} ${noun}` : noun.charAt(0).toUpperCase() + noun.slice(1),
    places.size === 1 ? [...places][0] : null,
    `shown ${shown}`,
  ]
    .filter(Boolean)
    .join(" · ");
}
```

In `Premium`, a filed-rate plan with no premium has no live price to be unavailable:

```jsx
function Premium({ plan }) {
  if (plan.monthly_premium === null) {
    if (exchangeFor(plan.state).filedRates) return <span>No filed rate for this ZIP code</span>;
    return (
      <>
        <span>Live price unavailable</span>
        {plan.premium_reference !== null && (
          <span className="plan-sub">
            {formatMoney(plan.premium_reference, { cents: true })}/mo at age {REFERENCE_AGE}
          </span>
        )}
      </>
    );
  }
  // unchanged below
```

In `PlanComparison`, compute `const exchange = exchangeFor(plans[0]?.state);` and `const year = plans[0]?.plan_year;`. Change the quality cell to:

```jsx
                  <td>
                    {plan.quality_rating !== null
                      ? `${plan.quality_rating} of 5`
                      : exchangeFor(plan.state).filedRates
                        ? "Not available"
                        : "Not rated"}
                  </td>
```

and replace the last footnote with:

```jsx
      <p className="plan-footnote">
        {exchange.filedRates
          ? `Premiums are CMS's published ${year} rates for the age shown, before any federal tax credit or state premium help.`
          : "Premiums are before any tax credit, which may lower what you pay."}{" "}
        Plans and prices change, so check today's at{" "}
        <a href={exchange.url} target="_blank" rel="noopener noreferrer">
          {exchange.name}
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
        .
      </p>
```

`frontend/src/features/profile/ProfileFields.jsx`:
- add `import { exchangeFor } from "../plans/exchanges";`;
- after the `!lookup.marketplaceState` note, add:

```jsx
      {lookup.status === "ready" && lookup.marketplaceState && exchangeFor(onlyCounty?.state).filedRates && (
        <p className="field-note">
          Plans in {onlyCounty.state} are sold on {exchangeFor(onlyCounty.state).name}. PolicyPal compares them from
          CMS's published plan data.
        </p>
      )}
```

`onlyCounty` is the first county. A ZIP spanning counties names its state the same way, since every county of one ZIP in `CA` is in `CA`.

- [ ] **Step 4: Run it and check it passes**

Run: `make ui-test && make ui-lint`
Expected: all pass, and lint is clean.

- [ ] **Step 5: Commit.** Add a CHANGELOG bullet: "Plan tables show the plan year, and for California name Covered California, say premiums are CMS's filed rates, and show quality ratings as 'Not available'."

```bash
git add frontend/src/features/plans/ frontend/src/features/profile/ CHANGELOG.md
git commit -m "Show California plans with their year, exchange and filed-rate note"
```

---

### Task 12: Docs, eval, end-to-end check, Azure seed, and the PR out of draft

**Files:**
- Create: `docs/decisions/0024-california-plans-from-the-sbe-puf.md`
- Create: `docs/findings/ca-sbe-puf.md`
- Create: `docs/runbooks/california.md`
- Modify: `README.md` (scope, and the California make target)
- Modify: `CLAUDE.md` (first "Built:" paragraph; it says "in the 30 states on HealthCare.gov")
- Modify: `scripts/eval_generation.py` (`PLAN_SEARCH_SET`, plus a Covered-California check)
- Modify: `docs/runbooks/deploy.md` (expected row counts after a seed include CA)

- [ ] **Step 1: Add the eval cases.** In `scripts/eval_generation.py`, append to `PLAN_SEARCH_SET`:

```python
    ("Compare silver plans for me", PlanProfile(zip_code="90012", age=40, county_fips="06037")),
    ("What bronze plans can I get?", PlanProfile(zip_code="90012", age=40, county_fips="06037")),
```

In `run_plan_searches`, after printing each answer, add:

```python
        if profile and profile.county_fips.startswith("06"):
            named = "Covered California" in result.text and "HealthCare.gov" not in result.text
            print(f"               exchange named correctly: {named}")
```

Run: `uv run python scripts/eval_generation.py`. It needs `OPENAI_API_KEY` and costs a few cents. Expected: both CA questions reach `search_plans`, and both print `exchange named correctly: True`.

- [ ] **Step 2: Run the end-to-end check with the Playwright plugin** against `make api` and `make ui-dev`:
  1. Sign up with ZIP `90012` and a 1986 date of birth. The profile shows "Plans in CA are sold on Covered California".
  2. Ask "Compare silver plans". Check:
     - a table captioned "2026 Silver plans · Los Angeles County, CA · …";
     - premiums shown;
     - the footnote "CMS's published 2026 rates";
     - a Covered California link to `https://www.coveredca.com/`.
  3. Ask "Show bronze plans". Plans are listed, and they are Expanded Bronze.
  4. Sign up with ZIP `75801` (TX). The table's footnote links HealthCare.gov. This is a regression check.

  Save screenshots under `$TMPDIR`, not the repo, and attach them to the PR.

- [ ] **Step 3: Write the docs**
  - **`docs/decisions/0024-california-plans-from-the-sbe-puf.md`.** Status: Accepted; amends ADR 0009 and 0010.
    - **Context:** the API doesn't serve CA; the PUF facts; the publication lag; Covered California's Terms.
    - **Decision:**
      - a CA-only loader;
      - filed rates in SQL;
      - "sold only where rated";
      - unlisted LA prefixes unpriced;
      - label and degrade;
      - in-network tier 1 individual cost shares only.
    - **Consequences:** CA data lags each open enrollment; a yearly manual re-check; `premium_reference` is NULL for CA.
  - **`docs/findings/ca-sbe-puf.md`:**
    - the 2026 profile from the spec's "The data, as verified" section;
    - the counts from Task 6 Step 6 and Task 7 Step 5;
    - the WHA finding (40 pairs);
    - the four unlisted LA ZIPs;
    - the note that the CSR variant labels match the API's.
  - **`docs/runbooks/california.md`,** the yearly routine:
    1. From May to Aug, `make ingest-ca-plans YEAR=<next>`, which exits 3 until the file is published.
    2. Re-check the CMS rating-area page against `rating_areas.py`.
    3. Re-check issuers against a federal issuer list and Covered California's carrier announcement.
    4. Check the load's printed counts.
    5. Seed Azure (deploy runbook step 5).
    6. Record the counts in the findings doc.
  - **`README.md`:** scope now reads "the 30 HealthCare.gov states, plus Covered California (California) from CMS's published plan data"; add `make ingest-ca-plans` to the command list.
  - **`CLAUDE.md`:** in the **Built:** paragraph, "in the 30 states on HealthCare.gov" becomes "in the 30 states on HealthCare.gov and in California (Covered California, from CMS's state-based exchange data)".
  - **`docs/runbooks/deploy.md` step 5:** add the CA plan count (190) to the expected-rows check.

- [ ] **Step 4: Run the full gate**

Run: `make check && make ui-test && make ui-lint`
Expected: green, with coverage ≥85% and `alembic check` clean.

- [ ] **Step 5: Commit, push, and mark the PR ready.** Add a CHANGELOG bullet: "ADR 0024, the California PUF findings and a yearly California runbook; README and CLAUDE.md scope now include Covered California."

```bash
git add docs/ README.md CLAUDE.md scripts/eval_generation.py CHANGELOG.md
git commit -m "Document California plans: ADR 0024, findings and the yearly runbook"
git push
gh pr edit 38 --body-file <updated body: Problem, Implementation (SP0 + SP1), Validation evidence (test counts, load counts, eval lines, Playwright screenshots), Security/DB/API impact>
gh pr ready 38
```

`git push` and `gh` must run outside the sandbox. Merge only when every CI check is green and no review comment is unresolved (CLAUDE.md).

- [ ] **Step 6: Seed Azure after the merge,** per `docs/runbooks/deploy.md` step 5: a dump of the local database, restored. Check the deployed API with a CA ZIP. This touches production, so confirm with the user before running it.

---

## Self-review

**Spec coverage.** Each spec section maps to its task:

| Spec section | Task |
| --- | --- |
| SP0 registry | 2 |
| Exchanges and plan year on sale | 1 |
| Schema | 4 |
| Reading | 6 |
| Loading and validation | 7 |
| Rating areas and issuers | 5 |
| Search | 8 |
| Bronze fix | 3 |
| Tools and prompts | 3, 9 |
| Profile | 10 |
| Frontend | 11 |
| Error handling | 6, 7, 8 |
| Security (no ZIP or age in logs; tested in 8 and 9) | 8, 9 |
| Testing | every task |
| Docs, ADRs 0024 and 0025, runbook | 2, 12 |
| Delivery | 3 (checkpoint), 12 |

The spec's "cross-check issuer names against a federal list" is a pre-merge open item. Task 12's runbook covers it for future years; for 2026 it is covered by the footprint check done in planning and recorded in `issuers.py`.

**Deliberate deviations from the spec,** each recorded in the spec itself:
- The API gains no `exchange_name` or `exchange_url` fields.
- Cost shares are in-network tier 1, individual only.
- A plan is "sold only where rated".
- Unlisted LA prefixes are shown unpriced rather than aborting the load.

**Type consistency.** These names are used identically across tasks:
- `filed_rate: tuple[int | None, int]`
- `premium_source` values `cms_live` and `cms_filed_rates`
- `CATALOG_SOURCE = "ca_sbe_puf"`, matching the check constraint
- `rate_age`, `resolve_place`, `_exchange`, `_freshness`
- `exchangeFor(state).filedRates`
