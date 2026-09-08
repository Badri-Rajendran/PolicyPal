"""Wikipedia corpus source: encyclopedic background on each insurance line.

Wikipedia is good at what insurance *is* — history, economics, how a line of
business works. It is poor at what a policyholder actually needs to do (see
`healthcare_gov.py`, which covers that register). Both are ingested.
"""
import re
import time

import wikipediaapi
from tqdm import tqdm

from src.policypal.config import settings

from ..chunking import (
    count_tokens,
    make_chunk,
    make_chunk_id,
    make_recursive_splitter,
    sanitize_name,
)
from ..constants import MARKDOWN, RAW, WIKI_ARTICLES
from .base import Source

# Wikipedia section titles survive Phase 2 as plain-text lines: short, capitalised,
# no terminal punctuation.
_SECTION_TITLE_RE = re.compile(r"^[A-Z][^\n.!?]{2,80}$")


class WikipediaSource(Source):
    name = "wikipedia"

    def fetch(self) -> None:
        print("\n=== Wikipedia: downloading articles ===")

        RAW.mkdir(parents=True, exist_ok=True)

        wiki = wikipediaapi.Wikipedia(
            user_agent="PolicyPalRAGProject/1.0 (personal project)",
            language="en",
        )

        for title in tqdm(WIKI_ARTICLES, desc="Wikipedia"):
            out_path = RAW / f"wiki_{sanitize_name(title)}.txt"

            if out_path.exists():
                continue

            try:
                page = wiki.page(title)
                if not page.exists():
                    print(f"  {title}: page not found")
                    continue

                out_path.write_text(page.text, encoding="utf-8")
                print(f"  {title}: downloaded ({len(page.text)} chars)")

                time.sleep(0.5)

            except Exception as e:  # noqa: BLE001 -- one bad article must not abort the whole batch
                print(f"  {title}: ERROR — {e}")

        txts = [f for f in RAW.iterdir() if f.name.startswith("wiki_")]
        print(f"  Total Wiki Text files: {len(txts)}")

    def normalize(self) -> None:
        print("\n=== Wikipedia: converting to markdown ===")

        MARKDOWN.mkdir(parents=True, exist_ok=True)

        for title in tqdm(WIKI_ARTICLES, desc="Wikipedia"):
            sanitized = sanitize_name(title)
            src = RAW / f"wiki_{sanitized}.txt"
            dst = MARKDOWN / f"wiki_{sanitized}.md"

            if not src.exists():
                print(f"  {title}: source not found, skipping")
                continue

            if dst.exists():
                continue

            text = src.read_text(encoding="utf-8")

            # Drop the trailing apparatus sections — they are link lists and
            # bibliographies, never answers.
            for heading in ("See also", "References", "External links"):
                text = re.sub(rf"\n==\s*{heading}\s*==.*", "", text, flags=re.DOTALL | re.IGNORECASE)

            # Strip citation markers [1], [23], etc.
            text = re.sub(r"\[\d+\]", "", text)

            if not text.strip().startswith("# "):
                text = f"# {title}\n\n{text}"

            text = re.sub(r"\n{3,}", "\n\n", text)

            dst.write_text(text.strip(), encoding="utf-8")
            print(f"  {title}: processed ({len(text):,} chars)")

        self._validate()

    def chunk_documents(self) -> list[dict]:
        print("\n=== Chunking Wikipedia articles ===")

        all_chunks: list[dict] = []

        for title in WIKI_ARTICLES:
            md_path = MARKDOWN / f"wiki_{sanitize_name(title)}.md"

            if not md_path.exists():
                print(f"  {title}: markdown not found, skipping")
                continue

            chunks = self._chunk_article(md_path.read_text(encoding="utf-8"), title)
            print(f"  {title}: {len(chunks)} chunks")
            all_chunks.extend(chunks)

        return all_chunks

    def _chunk_article(self, text: str, title: str) -> list[dict]:
        """Paragraph-first recursive splitting, tracking the current section."""
        sanitized_title = sanitize_name(title)

        # Remove the top-level # heading added during normalize()
        text = re.sub(r"^#\s+.+\n+", "", text, count=1).strip()

        splitter = make_recursive_splitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\\. ", "\n", " ", ""],
        )

        cur_section = title
        chunks: list[dict] = []

        for c_idx, raw_text in enumerate(splitter.split_text(text)):
            chunk_text = raw_text.strip()

            first_line = chunk_text.split("\n")[0].strip()
            if count_tokens(first_line) < 15 and _SECTION_TITLE_RE.match(first_line):
                cur_section = first_line

            # Prepend the article title (and section, if we're past the lead) so
            # BM25 and the embedding model both see context a mid-article chunk
            # wouldn't otherwise mention by name — e.g. a chunk that just says
            # "the deductible is..." still matches a "health insurance deductible"
            # query. A cheap, template-based stand-in for full contextual
            # retrieval (no per-chunk LLM call needed for a corpus this size).
            contextualized_text = (
                f"{title}\n{chunk_text}"
                if cur_section == title
                else f"{title}\n{cur_section}\n{chunk_text}"
            )

            chunks.append(make_chunk(
                text=chunk_text,
                contextualized_text=contextualized_text,
                chunk_id=make_chunk_id(self.name, sanitized_title, c_idx),
                source_file=f"wiki_{sanitized_title}.txt",
                doc_type="wikipedia",
                title=title,
                section=cur_section,
                chunk_index=c_idx,
            ))

        return chunks

    @staticmethod
    def _validate() -> None:
        print(f"\n{'File':<50} {'Chars':>8} {'##-count':>8} {'Status'}")
        print("-" * 78)

        missing = []

        for title in WIKI_ARTICLES:
            name = f"wiki_{sanitize_name(title)}.md"
            md = MARKDOWN / name

            if not md.exists():
                print(f"  {name:<48} {'---':>8} {'---':>8} MISSING")
                missing.append(name)
                continue

            text = md.read_text(encoding="utf-8")
            print(f"  {name:<48} {len(text):>8,} {text.count('##'):>8} OK")

        print()
        if missing:
            print(f"Issues found ({len(missing)}): {', '.join(missing)}")
        else:
            print("All validation checks passed.")
