"""Read CMS's California state-based exchange PUF: a zip of CSVs, into plain rows.

Pure functions, no database, so every rule here is unit-tested. The 2026 file
is profiled in docs/findings/ca-sbe-puf.md. Kept: individual-market,
on-exchange, medical plans. Cost shares: in-network tier 1, individual — the
only values the search reads, and the only ones whose API wording is verified.
"""
import csv
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

# The API's words (docs/findings/cms-marketplace-api.md); the search matches them exactly.
NO_CSR = "Exchange variant (no CSR)"
IN_NETWORK = "In-Network"
INDIVIDUAL = "Individual"

# (column, kind, cost_share_type). CMS spells TIER1 and TIER 1 both ways.
COST_SHARE_COLUMNS = (
    ("TEHB DED INN TIER 1 INDIVIDUAL", "deductible", "Combined Medical and Drug EHB Deductible"),
    ("MEHB DED INN TIER1 INDIVIDUAL", "deductible", "Medical EHB Deductible"),
    ("DEHB DED INN TIER1 INDIVIDUAL", "deductible", "Drug EHB Deductible"),
    ("TEHB INN TIER 1 INDIVIDUAL MOOP", "moop", "Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)"),
)
_PLAN_COLUMNS = ("BUSINESS YEAR", "STATE CODE", "ISSUER ID", "MARKET COVERAGE", "DENTAL ONLY PLAN",
                 "QHP NONQHP TYPE ID", "STANDARD COMPONENT ID", "PLAN ID", "PLAN MARKETING NAME", "PLAN TYPE",
                 "METAL LEVEL", "IS HSA ELIGIBLE", "NATIONAL NETWORK", "SERVICE AREA ID", "CSR VARIATION TYPE",
                 *(column for column, _, _ in COST_SHARE_COLUMNS))
_RATE_COLUMNS = ("PLAN ID", "RATING AREA ID", "AGE", "INDIVIDUAL RATE")
_AREA_COLUMNS = ("ISSUER ID", "SERVICE AREA ID", "COVER ENTIRE STATE", "COUNTY", "PARTIAL COUNTY", "ZIP CODE",
                 "MARKET COVERAGE", "DENTAL PLAN ONLY")

_MEMBER = re.compile(r"^CA(Plans|Rates|ServiceAreas)(\d{8})\.csv$")
_MONEY = re.compile(r"^\$?([0-9][0-9,]*(?:\.[0-9]+)?)$")
_PLAN_ID = re.compile(r"^\d{5}CA\d{7}-0[0-6]$")
_FIPS = re.compile(r"^06\d{3}$")
_ZIP = re.compile(r"^\d{5}$")
_AREA = re.compile(r"^Rating Area (\d{1,2})$")


class PufFormatError(ValueError):
    """The file is not the shape this reader was written against; nothing is loaded."""


@dataclass(frozen=True)
class PufPlan:
    hios_plan_id: str
    issuer_id: str
    marketing_name: str
    metal_level: str
    plan_type: str
    hsa_eligible: bool
    has_national_network: bool
    service_area_id: str


@dataclass(frozen=True)
class PufCostShare:
    hios_plan_id: str
    kind: str
    cost_share_type: str
    csr_variant: str
    amount: Decimal


@dataclass(frozen=True)
class PufServiceArea:
    issuer_id: str
    service_area_id: str
    countyfips: str | None  # None: the whole state
    zipcodes: tuple[str, ...] | None  # None: the whole county


@dataclass(frozen=True)
class Puf:
    label: str
    plans: tuple[PufPlan, ...]
    cost_shares: tuple[PufCostShare, ...]
    service_areas: tuple[PufServiceArea, ...]
    rates: dict[tuple[str, int, int], Decimal]  # (plan, rating area, age) -> monthly rate


def puf_money(text: str) -> Decimal | None:
    value = text.strip()
    if not value or value.lower() == "not applicable":
        return None
    match = _MONEY.match(value)
    if not match:
        raise PufFormatError(f"not an amount: {value!r}")
    return Decimal(match.group(1).replace(",", ""))


def age_key(text: str) -> int:
    if text == "0-14":
        return 14
    if text == "64 and over":
        return 64
    if text.isdigit() and 15 <= int(text) <= 63:
        return int(text)
    raise PufFormatError(f"unknown age band {text!r}")


def _yes(text: str) -> bool:
    if text not in ("Yes", "No"):
        raise PufFormatError(f"expected Yes or No, got {text!r}")
    return text == "Yes"


def _is_kept(row: dict) -> bool:
    return (row["MARKET COVERAGE"] == "Individual" and row["DENTAL ONLY PLAN"] == "No"
            and row["QHP NONQHP TYPE ID"] == "On the Exchange" and not row["PLAN ID"].endswith("-00"))


def _rows(archive: zipfile.ZipFile, name: str, required: tuple[str, ...]) -> list[dict]:
    try:
        text = archive.read(name).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PufFormatError(f"{name} is not UTF-8: {exc}") from None
    reader = csv.DictReader(io.StringIO(text))
    absent = [column for column in required if column not in (reader.fieldnames or ())]
    if absent:
        raise PufFormatError(f"{name} has no column {absent[0]!r}")
    return list(reader)


def _members(archive: zipfile.ZipFile) -> tuple[dict[str, str], str]:
    found: dict[str, tuple[str, str]] = {}
    for name in archive.namelist():
        match = _MEMBER.match(Path(name).name)
        if match:
            found[match.group(1)] = (name, match.group(2))
    missing = {"Plans", "Rates", "ServiceAreas"} - set(found)
    if missing:
        raise PufFormatError(f"the zip has no CA{', CA'.join(sorted(missing))} file")
    labels = {label for _, label in found.values()}
    if len(labels) != 1:
        raise PufFormatError(f"the files carry different dates: {sorted(labels)}")
    return {kind: name for kind, (name, _) in found.items()}, labels.pop()


def _plans(rows: list[dict], year: int) -> tuple[tuple[PufPlan, ...], tuple[PufCostShare, ...]]:
    kept = [row for row in rows if _is_kept(row)]
    if not kept:
        # A renamed market or exchange label would otherwise read as "no plans".
        raise PufFormatError("no individual, on-exchange medical plans in the file")
    for row in kept:
        if row["BUSINESS YEAR"] != str(year) or row["STATE CODE"] != "CA":
            raise PufFormatError(f"plan {row['PLAN ID']} is for plan year {row['BUSINESS YEAR']} "
                                 f"in {row['STATE CODE']}, not {year} in CA")
        if not _PLAN_ID.match(row["PLAN ID"]) or row["PLAN ID"][:14] != row["STANDARD COMPONENT ID"]:
            raise PufFormatError(f"unexpected plan id {row['PLAN ID']!r}")

    standard = {row["STANDARD COMPONENT ID"]: row for row in kept if row["PLAN ID"].endswith("-01")}
    bases = {row["STANDARD COMPONENT ID"] for row in kept}
    if missing := sorted(bases - set(standard)):
        raise PufFormatError(f"plan {missing[0]} has no -01 row")

    plans = tuple(
        PufPlan(hios_plan_id=base, issuer_id=row["ISSUER ID"], marketing_name=row["PLAN MARKETING NAME"].strip(),
                metal_level=row["METAL LEVEL"], plan_type=row["PLAN TYPE"], hsa_eligible=_yes(row["IS HSA ELIGIBLE"]),
                has_national_network=_yes(row["NATIONAL NETWORK"]), service_area_id=row["SERVICE AREA ID"])
        for base, row in sorted(standard.items())
    )

    shares: dict[tuple[str, str, str, str], PufCostShare] = {}
    for row in kept:
        base = row["STANDARD COMPONENT ID"]
        variant = NO_CSR if row["PLAN ID"].endswith("-01") else row["CSR VARIATION TYPE"]
        for column, kind, cost_share_type in COST_SHARE_COLUMNS:
            amount = puf_money(row[column])
            if amount is None:
                continue
            key = (base, kind, cost_share_type, variant)
            if key in shares:
                raise PufFormatError(f"plan {base} has two {variant!r} rows")
            shares[key] = PufCostShare(base, kind, cost_share_type, variant, amount)
    return plans, tuple(shares.values())


def _service_areas(rows: list[dict]) -> tuple[PufServiceArea, ...]:
    areas = []
    for row in rows:
        if row["MARKET COVERAGE"] != "Individual" or row["DENTAL PLAN ONLY"] != "No":
            continue
        if row["COVER ENTIRE STATE"] == "true":
            areas.append(PufServiceArea(row["ISSUER ID"], row["SERVICE AREA ID"], None, None))
            continue
        fips = row["COUNTY"].rsplit(" - ", 1)[-1].strip()
        if not _FIPS.match(fips):
            raise PufFormatError(f"service area {row['SERVICE AREA ID']}: unexpected county {row['COUNTY']!r}")
        zipcodes = None
        if row["PARTIAL COUNTY"] == "true":
            zipcodes = tuple(sorted({z.strip() for z in row["ZIP CODE"].split(",") if z.strip()}))
            if not zipcodes or not all(_ZIP.match(z) for z in zipcodes):
                raise PufFormatError(f"service area {row['SERVICE AREA ID']}: bad ZIP list for county {fips}")
        areas.append(PufServiceArea(row["ISSUER ID"], row["SERVICE AREA ID"], fips, zipcodes))
    return tuple(areas)


def _rates(rows: list[dict], plan_ids: set[str]) -> dict[tuple[str, int, int], Decimal]:
    rates: dict[tuple[str, int, int], Decimal] = {}
    for row in rows:
        if row["PLAN ID"] not in plan_ids:
            continue
        match = _AREA.match(row["RATING AREA ID"])
        if not match:
            raise PufFormatError(f"unexpected rating area {row['RATING AREA ID']!r}")
        rate = puf_money(row["INDIVIDUAL RATE"])
        if rate is None:
            raise PufFormatError(f"plan {row['PLAN ID']} has an empty rate")
        key = (row["PLAN ID"], int(match.group(1)), age_key(row["AGE"]))
        if key in rates and rates[key] != rate:
            raise PufFormatError(f"plan {row['PLAN ID']} has two rates for area {key[1]}, age {key[2]}")
        rates[key] = rate
    return rates


def read_puf(path: Path, year: int) -> Puf:
    with zipfile.ZipFile(path) as archive:
        members, label = _members(archive)
        plans, cost_shares = _plans(_rows(archive, members["Plans"], _PLAN_COLUMNS), year)
        rates = _rates(_rows(archive, members["Rates"], _RATE_COLUMNS), {p.hios_plan_id for p in plans})
        areas = _service_areas(_rows(archive, members["ServiceAreas"], _AREA_COLUMNS))
    return Puf(label=label, plans=plans, cost_shares=cost_shares, service_areas=areas, rates=rates)
