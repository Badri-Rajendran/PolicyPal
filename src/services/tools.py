"""The tools the answering model may call, and the boundary they cross (ADR 0010, 0014).

The model's arguments are generated text — possibly steered by a prompt
injection — so they are validated here before any query or outbound call,
whatever the schema promised. What goes back is data for the model, never
instructions, and carries neither the ZIP nor the age.
"""
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from src.core.db import get_session
from src.core.logging import get_logger
from src.core.marketplace_api import REFERENCE_AGE

from .plan_coverage import PlanCoverage, coverage_for
from .plan_search import PlanFilters, PlanResult, PlanSearchResult, search_plans
from .profile import PlanProfile
from .retrieval import RetrievedChunk

logger = get_logger(__name__)

MetalLevel = Literal["Catastrophic", "Bronze", "Expanded Bronze", "Silver", "Gold", "Platinum"]
PlanType = Literal["HMO", "PPO", "EPO", "POS", "Indemnity"]
SortBy = Literal["premium", "deductible"]

SEARCH_PLANS = "search_plans"
PLAN_COVERAGE = "plan_coverage"

MAX_COVERAGE_PLANS = 3
HiosPlanId = Annotated[str, StringConstraints(pattern=r"^\d{5}[A-Z]{2}\d{7}$")]


class SearchPlansArgs(BaseModel):
    # Strict: "34" is not an age and `true` is not a deductible.
    model_config = ConfigDict(extra="forbid", strict=True)

    zip_code: str | None = Field(pattern=r"^\d{5}$")
    age: int | None = Field(ge=0, le=120)
    metal_level: MetalLevel | None
    plan_type: PlanType | None
    max_deductible: int | None = Field(ge=0, le=100_000)
    county_fips: str | None = Field(pattern=r"^\d{5}$")
    sort_by: SortBy | None


class PlanCoverageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    plan_ids: list[HiosPlanId] = Field(min_length=1, max_length=MAX_COVERAGE_PLANS)
    question: str = Field(min_length=1, max_length=300)


def _nullable(json_type: str, description: str, enum: tuple | None = None) -> dict:
    schema = {"type": [json_type, "null"], "description": description}
    if enum:
        schema["enum"] = [*enum, None]
    return schema


# Strict mode: every property is required, and "not stated" is null.
TOOLS = [{
    "type": "function",
    "function": {
        "name": SEARCH_PLANS,
        "description": (
            "Search real ACA Marketplace health plans sold through HealthCare.gov in the user's "
            "county, with monthly premiums for the user's age. Call it for any question about "
            "specific plans, their premiums, deductibles or out-of-pocket maximums, or comparing "
            "plans. The user's saved ZIP code, age and county are filled in for you: leave zip_code "
            "and age null unless the question itself names a different one. Never guess either."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "zip_code": _nullable(
                    "string",
                    "Only a 5-digit ZIP code the question names for this search, such as a relative's "
                    "or one the user is moving to. Null uses the user's saved ZIP code.",
                ),
                "age": _nullable(
                    "integer",
                    "Only an age the question names for this search, such as a child's or a parent's. "
                    "Null uses the user's own age.",
                ),
                "metal_level": _nullable("string", "Only plans of this metal level.", get_args(MetalLevel)),
                "plan_type": _nullable("string", "Only plans of this network type.", get_args(PlanType)),
                "max_deductible": _nullable("integer", "Only plans whose yearly deductible is at most this, in USD."),
                "county_fips": _nullable(
                    "string",
                    "Only when an earlier search_plans result listed several counties for this ZIP "
                    "and the user chose one: that county's county_fips.",
                ),
                "sort_by": _nullable(
                    "string",
                    "\"deductible\" whenever the user asks about low or the lowest deductibles, "
                    "since only the first 10 plans come back; otherwise null, which orders by premium.",
                    get_args(SortBy),
                ),
            },
            "required": list(SearchPlansArgs.model_fields),
            "additionalProperties": False,
        },
    },
}, {
    "type": "function",
    "function": {
        "name": PLAN_COVERAGE,
        "description": (
            "Read what specific plans' Summary of Benefits and Coverage says: what a plan covers "
            "or excludes, its copays, coinsurance and limits for a service, and its coverage "
            "examples. Call it for any question about what a particular plan covers or charges for "
            "a service. Plan IDs come from a search_plans result or from <plans_shown>; to learn a "
            "plan's ID first, call search_plans."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "plan_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"1 to {MAX_COVERAGE_PLANS} plan IDs, exactly as given, e.g. 12345NH0010001.",
                },
                "question": {
                    "type": "string",
                    "description": "What to look up, as a short standalone question, e.g. \"Is an MRI covered, "
                                   "and what does it cost?\" No personal details.",
                },
            },
            "required": list(PlanCoverageArgs.model_fields),
            "additionalProperties": False,
        },
    },
}]


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    plans: tuple[PlanResult, ...] = ()
    # SBC passages the answer may cite (ADR 0014).
    chunks: tuple[RetrievedChunk, ...] = ()
    # What the user still has to supply: "zip_code", "age" or "county".
    needs_input: tuple[str, ...] = ()


def _outcome(status: str, **fields) -> ToolOutcome:
    # Data only. What to do for each status is in the system prompt, so a
    # result never has to be read as instructions.
    return ToolOutcome(json.dumps({"status": status, **fields}, default=str))


def _plan_row(plan: PlanResult) -> dict:
    row = {
        "source": "plan",
        "plan_id": plan.hios_plan_id,
        "name": plan.name,
        "issuer": plan.issuer,
        "metal_level": plan.metal_level,
        "plan_type": plan.plan_type,
        "monthly_premium": plan.monthly_premium,
        "hsa_eligible": plan.hsa_eligible,
        "quality_rating": plan.quality_rating,
    }
    if not plan.premium_is_live:
        row[f"reference_premium_age_{REFERENCE_AGE}"] = plan.premium_reference
    # Named by what they cover, never a null to interpret: a plan with a
    # separate drug deductible read as "deductible: $0" looks free to use.
    if plan.drug_deductible is None:
        row["deductible"] = plan.deductible
    else:
        row["medical_deductible"] = plan.deductible
        row["drug_deductible"] = plan.drug_deductible
    row["out_of_pocket_max"] = plan.out_of_pocket_max
    return row


def _render(result: PlanSearchResult) -> ToolOutcome:
    if result.status == "not_marketplace_state":
        return _outcome(result.status, state=result.state)
    if result.status == "ambiguous_county":
        counties = [{"county_fips": c.fips, "county": c.name, "state": c.state} for c in result.counties]
        outcome = _outcome(result.status, counties=counties)
        return ToolOutcome(outcome.content, needs_input=("county",))
    if result.status != "ok":
        county = f"{result.county.name}, {result.county.state}" if result.county else None
        return _outcome(result.status, county=county, plan_year=result.plan_year,
                        catastrophic_plans_excluded=result.catastrophic_excluded)

    payload = {
        "status": "ok",
        "plan_year": result.plan_year,
        "county": f"{result.county.name}, {result.county.state}",
        "total_matching": result.total_matching,
        "showing": len(result.plans),
        "catastrophic_plans_excluded": result.catastrophic_excluded,
        "plans": [_plan_row(p) for p in result.plans],
    }
    return ToolOutcome(json.dumps(payload, default=str), plans=result.plans)


def _coverage_row(coverage: PlanCoverage) -> dict:
    row = {"plan_id": coverage.plan_id, "status": coverage.status}
    if coverage.status == "not_found":
        return row
    row |= {"name": coverage.name, "issuer": coverage.issuer, "plan_year": coverage.plan_year,
            "sbc_url": coverage.sbc_url}
    if coverage.passages:
        row["passages"] = [{"source": p.source, "text": p.content} for p in coverage.passages]
    return row


def _parse(model: type[BaseModel], name: str, raw_arguments: str) -> BaseModel | ToolOutcome:
    """The validated arguments, or the invalid_arguments result to send back."""
    try:
        return model.model_validate_json(raw_arguments)
    except ValidationError as exc:
        # include_input=False: the rejected value may be the user's ZIP.
        errors = exc.errors(include_input=False, include_url=False)
        logger.info("%s arguments rejected: %s", name, sorted({e["type"] for e in errors}))
        problems = [f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in errors]
        return _outcome("invalid_arguments", problems=problems)


def run_tool(name: str, raw_arguments: str, profile: PlanProfile | None = None,
             plan_years: Mapping[str, int] | None = None) -> ToolOutcome:
    """Run one model-requested tool call. Never raises: a failure is a result.

    `profile` fills whatever the question did not name, here on the server:
    the user's saved ZIP code and age never pass through the model (ADR 0012).
    Its county applies only to its own ZIP code. `plan_years` holds the year
    of each plan the user has been shown, so coverage is read for that year.

    An exception escaping here would bypass the chat route's handler for
    OpenAI errors, fail the request and roll back the spend it recorded.
    """
    if name == PLAN_COVERAGE:
        return _plan_coverage(raw_arguments, plan_years)
    if name != SEARCH_PLANS:
        logger.warning("model requested an unknown tool")
        return _outcome("error", detail="unknown tool")

    args = _parse(SearchPlansArgs, name, raw_arguments)
    if isinstance(args, ToolOutcome):
        return args

    zip_code = args.zip_code or (profile.zip_code if profile else None)
    age = args.age if args.age is not None else (profile.age if profile else None)
    county_fips = args.county_fips or (
        profile.county_fips if profile and zip_code == profile.zip_code else None
    )

    missing = tuple(f for f, value in (("zip_code", zip_code), ("age", age)) if value is None)
    if missing:
        logger.info("search_plans needs input: %s", list(missing))
        outcome = _outcome("needs_input", missing=list(missing))
        return ToolOutcome(outcome.content, needs_input=missing)

    filters = PlanFilters(
        metal_level=args.metal_level,
        plan_type=args.plan_type,
        max_deductible=args.max_deductible,
        sort_by=args.sort_by or "premium",
    )
    try:
        with get_session() as session:
            result = search_plans(session, zip_code=zip_code, age=age,
                                  county_fips=county_fips, filters=filters)
    except Exception as exc:  # noqa: BLE001 — see the docstring
        # The type only: a database error's text carries its bound parameters, the ZIP among them.
        logger.error("search_plans failed: %s", type(exc).__name__)
        return _outcome("error")

    logger.info("search_plans: %s", result.status)
    return _render(result)


def _plan_coverage(raw_arguments: str, plan_years: Mapping[str, int] | None) -> ToolOutcome:
    args = _parse(PlanCoverageArgs, PLAN_COVERAGE, raw_arguments)
    if isinstance(args, ToolOutcome):
        return args

    plan_ids = list(dict.fromkeys(args.plan_ids))
    try:
        with get_session() as session:
            coverages = coverage_for(session, plan_ids, args.question, plan_years)
    except Exception as exc:  # noqa: BLE001 — see run_tool
        logger.error("plan_coverage failed: %s", type(exc).__name__)
        return _outcome("error")

    logger.info("plan_coverage: %s", [c.status for c in coverages])
    payload = {"status": "ok", "plans": [_coverage_row(c) for c in coverages]}
    chunks = tuple(p for c in coverages for p in c.passages)
    return ToolOutcome(json.dumps(payload, default=str), chunks=chunks)
