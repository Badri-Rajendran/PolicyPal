#!/usr/bin/env python3
"""Phase 1: Download all corpus sources."""

import re
import time
import wikipediaapi
from tqdm import tqdm
from .constants import RAW, WIKI_ARTICLES

def wikipedia_data():
    print("\n=== Phase 1: Downloading Wikipedia Articles ===")
    
    RAW.mkdir(parents=True, exist_ok=True)

    wiki = wikipediaapi.Wikipedia(
        user_agent="PolicyPalRAGProject/1.0 (personal project)",
        language="en",
    )

    for title in tqdm(WIKI_ARTICLES, desc="Wikipedia"):
        sanitized = re.sub(r"[^\w]+", "_", title).strip("_")
            
        out_path = RAW / f"wiki_{sanitized}.txt"

        if out_path.exists():
            print(f"  {title}: already exists, skipping")
            continue

        try:
            page = wiki.page(title)
            if not page.exists():
                print(f"  {title}: page not found")
                continue
            
            out_path.write_text(page.text, encoding="utf-8")
            
            print(f"  {title}: downloaded ({len(page.text)} chars)")
            
            time.sleep(0.5)
        
        except Exception as e:
            print(f"  {title}: ERROR — {e}")
    
    _print_summary()

def _print_summary():
    raw_files = list(RAW.iterdir())

    txts = [file for file in raw_files if file.suffix == ".txt"]

    print(f"  Total Wiki Text files: {len(txts)}")