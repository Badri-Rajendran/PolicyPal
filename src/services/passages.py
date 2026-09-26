"""Cited passages, as the Sources panel shows them (ADR 0027)."""
import hashlib


def content_hash(text: str) -> str:
    """The passage text's fingerprint, stored with each citation."""
    return hashlib.sha256(text.encode()).hexdigest()
