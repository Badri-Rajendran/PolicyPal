def count_tokens(text: str) -> int:
    """Approximate token count as 1.35x the word count."""
    return int(len(text.split()) * 1.35)
