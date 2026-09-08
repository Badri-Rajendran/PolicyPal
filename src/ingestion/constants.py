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
    "Crop insurance"
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

RAW = Path("data/corpus/raw")

MARKDOWN = Path("data/corpus/markdown")

CHUNKS_DIR = Path("data/corpus/chunks")

INDEX_DIR = Path("data/corpus/indices")
