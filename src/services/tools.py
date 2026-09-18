"""The one tool the answering model may call, and the boundary it crosses (ADR 0010).

The model's arguments are generated text — possibly steered by a prompt
injection — so they are validated here before any query or outbound call,
whatever the schema promised. What goes back is data for the model, never
instructions, and carries neither the ZIP nor the age.
"""
import json
from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.db import get_session
from src.core.logging import get_logger
from src.core.marketplace_api import REFERENCE_AGE

from .plan_search import PlanFilters, PlanResult, PlanSearchResult, search_plans

logger = get_logger(__name__)

MetalLevel = Literal["Catastrophic", "Bronze", "Expanded Bronze", "Silver", "Gold", "Platinum"]
PlanType = Literal["HMO", "PPO", "EPO", "POS", "Indemnity"]
SortBy = Literal["premium", "deductible"]

SEARCH_PLANS = "search_plans"


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
            "plans. Pass null for anything the user has not stated in this conversation; never "
            "guess a ZIP code or an age."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "zip_code": _nullable("string", "The user's 5-digit US ZIP code."),
                "age": _nullable("integer", "The age of the person to be covered."),
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
}]


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    plans: tuple[PlanResult, ...] = ()
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


def run_tool(name: str, raw_arguments: str) -> ToolOutcome:
    """Run one model-requested tool call. Never raises: a failure is a result.

    An exception escaping here would bypass the chat route's handler for
    OpenAI errors, fail the request and roll back the spend it recorded.
    """
    if name != SEARCH_PLANS:
        logger.warning("model requested an unknown tool")
        return _outcome("error", detail="unknown tool")

    try:
        args = SearchPlansArgs.model_validate_json(raw_arguments)
    except ValidationError as exc:
        # include_input=False: the rejected value may be the user's ZIP.
        errors = exc.errors(include_input=False, include_url=False)
        logger.info("search_plans arguments rejected: %s", sorted({e["type"] for e in errors}))
        problems = [f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in errors]
        return _outcome("invalid_arguments", problems=problems)

    missing = tuple(f for f in ("zip_code", "age") if getattr(args, f) is None)
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
            result = search_plans(session, zip_code=args.zip_code, age=args.age,
                                  county_fips=args.county_fips, filters=filters)
    except Exception as exc:  # noqa: BLE001 — see the docstring
        # The type only: a database error's text carries its bound parameters, the ZIP among them.
        logger.error("search_plans failed: %s", type(exc).__name__)
        return _outcome("error")

    logger.info("search_plans: %s", result.status)
    return _render(result)
