from pathlib import Path
import tiktoken as tt

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

RAW = Path("data/corpus/raw")

MARKDOWN = Path("data/corpus/markdown")

CHUNKS_DIR = Path("data/corpus/chunks")

TOKENIZER = tt.encoding_for_model("gpt2")