"""The committed source registry (ADR 0025): every source, and whether it may be used.

Read with the standard library's tomllib. An invalid registry fails when it
loads, so a bad edit cannot quietly enable a source.
"""
import tomllib
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name("registry.toml")

KINDS = {"corpus", "catalog", "sbc_host", "directory"}
PERMISSIONS = {"public_domain", "open_license", "written_permission", "pending_review", "denied"}
APPROVED = {"public_domain", "open_license", "written_permission"}
COMMERCIAL_USE = {"yes", "no", "review"}
ROBOTS = {"allowed", "disallowed", "unavailable", "not_applicable"}
ACCESS = {"api", "download", "crawl", "manual", "link"}

_REQUIRED = ("id", "name", "publisher", "scope_urls", "kind", "jurisdiction", "license", "license_url",
             "permission_status", "commercial_use", "robots", "access", "verified_on", "enabled",
             "removal", "notes")
_OPTIONAL = ("robots_checked_on",)
_CHOICES = {"kind": KINDS, "permission_status": PERMISSIONS, "commercial_use": COMMERCIAL_USE,
            "robots": ROBOTS, "access": ACCESS}


class RegistryError(ValueError):
    """The registry file breaks a rule; the message names the entry and field."""


class SourceNotApprovedError(Exception):
    """A source that is unregistered or disabled was asked for."""


@dataclass(frozen=True)
class RegisteredSource:
    id: str
    name: str
    publisher: str
    scope_urls: tuple[str, ...]
    kind: str
    jurisdiction: str
    license: str
    license_url: str
    permission_status: str
    commercial_use: str
    robots: str
    robots_checked_on: date | None
    access: str
    verified_on: date
    enabled: bool
    removal: str
    notes: str


def _entry(raw: dict) -> RegisteredSource:
    label = raw.get("id", "<no id>")
    for field in _REQUIRED:
        if field not in raw:
            raise RegistryError(f"{label}: missing {field}")
    if unknown := sorted(set(raw) - set(_REQUIRED) - set(_OPTIONAL)):
        raise RegistryError(f"{label}: unknown field {unknown[0]}")
    for field, allowed in _CHOICES.items():
        if raw[field] not in allowed:
            raise RegistryError(f"{label}: {field} {raw[field]!r} is not one of {sorted(allowed)}")
    if raw["robots"] != "not_applicable" and not isinstance(raw.get("robots_checked_on"), date):
        raise RegistryError(f"{label}: robots_checked_on is required when robots is {raw['robots']!r}")
    if not isinstance(raw["verified_on"], date):
        raise RegistryError(f"{label}: verified_on must be a date")
    if not isinstance(raw["enabled"], bool):
        raise RegistryError(f"{label}: enabled must be true or false")
    if raw["enabled"] and raw["permission_status"] not in APPROVED:
        raise RegistryError(f"{label}: enabled needs permission_status in {sorted(APPROVED)}")
    jurisdiction = raw["jurisdiction"]
    if not (isinstance(jurisdiction, str) and len(jurisdiction) == 2 and jurisdiction.isalpha()
            and jurisdiction.isupper()):
        raise RegistryError(f"{label}: jurisdiction must be 'US' or a state code")
    return RegisteredSource(**{**raw, "scope_urls": tuple(raw["scope_urls"]),
                               "robots_checked_on": raw.get("robots_checked_on")})


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, RegisteredSource]:
    with open(path, "rb") as handle:
        try:
            entries = tomllib.load(handle).get("source", [])
        except tomllib.TOMLDecodeError as exc:
            raise RegistryError(f"{path.name} is not valid TOML: {exc}") from None
    registry: dict[str, RegisteredSource] = {}
    for raw in entries:
        entry = _entry(raw)
        if entry.id in registry:
            raise RegistryError(f"duplicate id {entry.id!r}")
        registry[entry.id] = entry
    return registry


@cache
def _committed() -> dict[str, RegisteredSource]:
    return load_registry()


def is_enabled(source_id: str) -> bool:
    entry = _committed().get(source_id)
    return entry is not None and entry.enabled


def require_enabled(source_id: str) -> RegisteredSource:
    entry = _committed().get(source_id)
    if entry is None:
        raise SourceNotApprovedError(f"{source_id} is not in the source registry")
    if not entry.enabled:
        raise SourceNotApprovedError(f"{source_id} is disabled ({entry.permission_status})")
    return entry
