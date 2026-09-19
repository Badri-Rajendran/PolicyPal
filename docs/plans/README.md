# PolicyPal roadmap

PolicyPal answers *definitional* insurance questions from a RAG corpus
(Wikipedia + HealthCare.gov). These documents plan its expansion into
*comparative* questions about real, purchasable health plans — and eventually
situational coverage questions from plan documents.

Each phase is a reference document to execute from, not a commitment to build
in order tomorrow. Phase 0 and Phase 1 are the immediate work; Phases 2–4 are
written down now so the decisions they depend on are made deliberately rather
than discovered late.

## Phases

| Phase | Goal | Status |
| --- | --- | --- |
| [0](phase-0-hosted-llm.md) | Swap the local LLM for a hosted one | Complete (ADR 0008) |
| [1](phase-1-marketplace-api.md) | Marketplace API catalog + plan comparison | In progress — Steps 1–5 of 6 done; 5b (user profile) next |
| [2](phase-2-sbc-narrow-slice.md) | SBC ingestion, one or two states | Documented only |
| [3](phase-3-sbc-top-issuers.md) | SBC for the largest issuers nationally | Documented only |
| [4](phase-4-sbc-full-coverage.md) | SBC across all 30 HealthCare.gov states | Documented only |

Verified, dated facts about external systems (API behavior confirmed against
a real key, not just documentation) live in
[`docs/findings/`](../findings/) — e.g.
[`cms-marketplace-api.md`](../findings/cms-marketplace-api.md) — separately
from these phase documents, so they stay findable after a phase's status
moves on.

Phase 0 ships green on its own before Phase 1 starts. If retrieval or
abstention quality regresses afterwards, that ordering makes it unambiguous
which change caused it.

## Target architecture

Retrieval is unconditional. It runs before the model on every prompt, and plan
tools are available alongside it:

```
user prompt
  → RAG retrieves chunks (local embeddings + rerank)
  → chunks go into the LLM context
  → LLM also has plan tools available
  → LLM answers from both together
```

Corpus chunks, plan rows and (from Phase 2) SBC chunks share one context.
They are not kept apart; instead each context item is tagged with its source
type and identifier so a citation resolves back to whatever produced it.

## What the research established

The starting premise was that the CMS Marketplace API covers "all health
insurance data from all providers." It does not.

| Dimension | Covered | Missing |
| --- | --- | --- |
| Geography | 27 FFM + 3 SBM-FP (AR, OK, OR) = **30 states** | 21 states + DC (CA, NY, WA, CO, MA…) |
| Segment | ACA individual/family, **24.2M** people | Employer **164M (53.8%)**, Medicare 19.1%, Medicaid 17.6% |
| Content | Premiums, deductibles, OOP max, copays, EHB categories, formulary | No contract language, no exclusions, no prior-auth rules |

That is roughly **7% of insured Americans across 30 of 51 jurisdictions**.
Kaiser Permanente's largest market, California, runs a state-based exchange
and is absent entirely.

### Evidence of Coverage is not obtainable; the SBC is

Plan contract language was the obvious way to answer "will this be covered?"
It is largely unavailable before purchase:

> "Many health plans do not provide the Evidence of Coverage documents until
> you have purchased a health plan and are a paid member."
> — [National Disability Navigator Resource Collaborative](https://nationaldisabilitynavigator.org/ndnrc-materials/fact-sheets/fact-sheet-2/)

California requires plans to provide it on request pre-enrollment; most states
do not. Indexing EOCs would mean buying every plan first.

The **Summary of Benefits and Coverage** replaces it and is better suited
anyway:

| | EOC | SBC |
| --- | --- | --- |
| Obtainable pre-purchase | Usually not | **Federally required** when shopping, and within 7 business days of request |
| Format | Bespoke per insurer, 100–200 pages | **Standardized federal template**, ~8 pages |
| Exclusions | Yes | Yes — "Services Your Plan Does NOT Cover" |
| Worked coverage examples | Yes | Yes |
| Copyright exposure | High — bespoke legal contract | Lower — government-mandated form |

The standardized format is the real advantage: identical section headings
across all 183 issuers means chunking can be structure-aware, and the same
heading always means the same thing.

### SBCs and the Marketplace API are complementary

| | SBC | Marketplace API |
| --- | --- | --- |
| Deductible, OOP max | Yes | Yes |
| Copays / coinsurance per service | Yes | Yes |
| Exclusions, limitations | Yes | No |
| Coverage examples | Yes | No |
| **Premium** | **No** — deliberately omitted, varies by age/income/tobacco | Yes |
| **Plan discovery by ZIP** | No | Yes |
| Quality ratings, metal level, issuer metadata | No | Yes |

Neither replaces the other. The API is the **catalog**; SBCs are the **fine
print**. SBC collection depends on the API regardless of how the two are
merged at retrieval time, because plan IDs and document URLs come from the
catalog — which is why Phase 1 precedes Phase 2.

## Scope decisions

| Decision | Choice |
| --- | --- |
| Capability | Comparison + generic coverage Q&A |
| Personalization | **ZIP + age only.** No income, tobacco, or household size |
| UI surface | Structured plan cards inline in chat |
| Retrieval | Unconditional on every prompt; plan tools alongside |
| Context | Corpus, plan and SBC results merge freely, provenance tagged |

### Rejected, deliberately

**Personalized "which plan should I buy" recommendation.** Recommending
specific coverage is insurance producer territory — the NAIC model act
prohibits soliciting or negotiating insurance without a state license, and
requirements vary per state. It would also reverse
[ADR 0004](../decisions/0004-retrieval-tuning.md), which made abstention a
*measured* property with a regression floor and explicitly records
*"Which insurance company should I buy from?"* as a question the system
should refuse.

**Employer, Medicare and Medicaid plans.** No public catalog exists. Employer
coverage alone is 164M people and has no equivalent of the Marketplace API.

**State-based exchange plans.** 21 states and DC run their own marketplaces
and are not in the Marketplace API. Supporting them would mean a separate
integration per state.

**Subsidized premium calculation.** Requires household income. Phase 1 shows
unsubsidized premiums and links to HealthCare.gov instead.

## Sources

- [CMS Marketplace API](https://developer.cms.gov/marketplace-api) · [spec](https://developer.cms.gov/marketplace-api/api-spec) · [key request](https://developer.cms.gov/marketplace-api/key-request.html)
- [CMS — Interoperability and Patient Access Final Rule (CMS-9115-F)](https://www.cms.gov/initiatives/burden-reduction/overview/interoperability/policies-regulations/cms-interoperability-patient-access-final-rule-cms-9115-f)
- [CMS — QHP machine-readable index spec](https://github.com/CMSgov/QHP-provider-formulary-APIs/blob/master/index_document.md)
- [45 CFR 147.212 — Transparency in coverage](https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-B/part-147/section-147.212)
- [Plan Year 2026 Marketplace Plans and Prices Fact Sheet](https://cms.gov/newsroom/fact-sheets/plan-year-2026-marketplace-plans-prices-fact-sheet) — 183 QHP issuers, 30 states
- [NAIC — Producer Licensing](https://content.naic.org/insurance-topics/producer-licensing)
