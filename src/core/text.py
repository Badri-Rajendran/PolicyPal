def count_tokens(text: str) -> int:
    """Approximate token count as 1.35x the word count.

    Deliberately an approximation, not a tokenizer. It decides chunk
    boundaries, so switching to an exact count would re-chunk the corpus and
    move every stored chunk_id — a re-ingest and a floor re-measure, to bound
    a history budget and a chunk size that are both already generous.
    """
    return int(len(text.split()) * 1.35)
