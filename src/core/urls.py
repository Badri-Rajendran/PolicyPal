"""URL checks shared by ingestion and the API."""
import ipaddress
from urllib.parse import urlsplit


def unsafe_reason(url: str) -> str | None:
    """Why `url` must not be fetched, or None. Also vets a manifest's links before they are stored,
    and any link the API returns to a browser (ADR 0027)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        return "not an https URL"
    if not host or "." not in host or host == "localhost" or host.endswith((".local", ".internal")):
        return "not a public host name"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return "an IP address, not a host name"
