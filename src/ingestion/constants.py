from pathlib import Path

WIKI_ARTICLES = [
    "Health_insurance",
    "Life insurance",
    "Disability insurance",
    "Long-term care insurance",
    "Home insurance",
    "Renters' insurance",
    "Property insurance",
    "Vehicle insurance",
    "Liability insurance",
    "Travel insurance",
    "Pet insurance",
    "Flood insurance",
    "Earthquake insurance",
    "Title insurance",
    "Lenders mortgage insurance",
    "Business interruption insurance",
    "Workers' compensation",
    "Professional liability insurance",
    "Directors and officers liability insurance",
    "Key person insurance",
    "Trade credit insurance",
    "Cyber insurance",
    "Marine insurance",
    "Aviation insurance",
    "Crop insurance",
    # Added to close gaps the coverage eval named: users ask whether they need
    # umbrella cover, and how term compares to whole life. Neither Wikipedia's
    # other articles nor HealthCare.gov (health-only) answered these.
    "Umbrella insurance",
    "Term life insurance",
    "Whole life insurance",
]

# HealthCare.gov publishes its consumer education content as JSON for reuse
# (https://www.healthcare.gov/developers/). As a work of the US federal
# government it is public domain under 17 U.S.C. § 105. See ADR 0003.
HEALTHCARE_GOV_BASE_URL = "https://www.healthcare.gov/api"

# collection name -> raw filename. "glossary" is the CMS Uniform Glossary that
# insurers must use in Summary of Benefits documents, so it matches the
# vocabulary printed on a user's own paperwork.
HEALTHCARE_GOV_COLLECTIONS = {
    "glossary": "hcg_glossary.json",
    "articles": "hcg_articles.json",
}

HEALTHCARE_GOV_USER_AGENT = "PolicyPalRAGProject/1.0 (personal project)"

# CMS Marketplace API — the plan catalog, not the corpus. See
# docs/findings/cms-marketplace-api.md for what it verifiably returns.
MARKETPLACE_API_BASE_URL = "https://marketplace.api.healthcare.gov/api/v1"

# The states this API serves: marketplace_model FFM (27) plus SupportedSBM
# (AR, OK, OR), per GET /states for plan year 2026. It exists to validate
# `--states` and to expand ALL — it does not choose what gets ingested. The
# other 21 states and DC run their own exchanges, and the API rejects them
# ("state is not a valid marketplace state"), so failing locally is kinder.
MARKETPLACE_STATES = (
    "AK", "AL", "AR", "AZ", "DE", "FL", "HI", "IA", "IN", "KS",
    "LA", "MI", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "OH",
    "OK", "OR", "SC", "SD", "TN", "TX", "UT", "WI", "WV", "WY",
)

RAW = Path("data/corpus/raw")

PLANS_RAW = Path("data/plans/raw")

MARKDOWN = Path("data/corpus/markdown")

CHUNKS_DIR = Path("data/corpus/chunks")

INDEX_DIR = Path("data/corpus/indices")
