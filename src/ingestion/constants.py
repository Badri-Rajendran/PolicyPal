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

# Sent on every fetch this project makes, so a site can tell who is asking.
USER_AGENT = "PolicyPalRAGProject/1.0 (personal project)"

RAW = Path("data/corpus/raw")

PLANS_RAW = Path("data/plans/raw")

# Downloaded SBC PDFs, every one kept for good (ADR 0016). Never committed or
# served: ADR 0013. A file rejected as another year's is moved aside, not
# deleted, so a corrected one can be downloaded in its place.
SBC_RAW = Path("data/sbc/raw")
SBC_REJECTED = Path("data/sbc/rejected")
# The file a changed one replaced, kept for good as well (ADR 0019).
SBC_ARCHIVE = Path("data/sbc/archive")

MARKDOWN = Path("data/corpus/markdown")

CHUNKS_DIR = Path("data/corpus/chunks")
