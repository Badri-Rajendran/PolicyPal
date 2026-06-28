#!/usr/bin/env python3
"""Phase 2: Convert raw sources to clean markdown."""

import re
from tqdm import tqdm
from .constants import WIKI_ARTICLES, RAW, MARKDOWN

def sanitize_name(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name).strip("_")

def wikipedia_data():
    print("\n=== Phase 2.1: Processing Wikipedia Articles ===")

    MARKDOWN.mkdir(exist_ok=True)

    for title in tqdm(WIKI_ARTICLES, desc="Wikipedia"):
        sanitized = sanitize_name(title)
        src = RAW / f"wiki_{sanitized}.txt"
        dst = MARKDOWN / f"wiki_{sanitized}.md"

        if not src.exists():
            print(f"  {title}: source not found, skipping")
            continue

        if dst.exists():
            print(f"  {title}: already processed, skipping")
            continue

        text = src.read_text(encoding="utf-8")

        # Strip from == See also == to end
        text = re.sub(r"\n==\s*See also\s*==.*", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip from == References == to end
        text = re.sub(r"\n==\s*References\s*==.*", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip from == External links == to end
        text = re.sub(r"\n==\s*External links\s*==.*", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip citation markers [1], [23], etc.
        text = re.sub(r"\[\d+\]", "", text)

        # Add top-level heading if not present
        if not text.strip().startswith("# "):
            text = f"# {title}\n\n{text}"

        # Normalize blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        dst.write_text(text.strip(), encoding="utf-8")
        
        print(f"  {title}: processed ({len(text):,} chars)")
    
    validate()


# Phase 2.2: Validation

def validate():
    print("\n=== Phase 2.2: Validation ===")

    print(f"\n{'File':<50} {'Chars':>8} {'##-count':>8} {'Status'}")
    print("-" * 78)

    issues = []

    for title in WIKI_ARTICLES:
        sanitized = sanitize_name(title)
        
        md = MARKDOWN / f"wiki_{sanitized}.md"
        name = f"wiki_{sanitized}.md"
        
        if not md.exists():
            print(f"  {name:<48} {'---':>8} {'---':>8} MISSING")
            issues.append(f"MISSING: {name}")
            continue
        
        text = md.read_text(encoding="utf-8")
        
        n_sections = text.count("##")
        
        print(f"  {name:<48} {len(text):>8,} {n_sections:>8} OK")

    print()
    
    if issues:
        print(f"Issues found ({len(issues)}):")

        error_msg = " \n".join(issues)

        print("Issues are :", error_msg)
        
    else:
        print("All validation checks passed.")