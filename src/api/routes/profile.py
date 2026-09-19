import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from src.api.deps import ValidationFailedError, get_current_user, get_db, parse_body
from src.api.limiter import limiter
from src.schemas.profile import (
    CountiesResponse,
    CountyResponse,
    ProfileResponse,
    ProfileUpdateRequest,
)
from src.services.profile import (
    ProfileInvalidError,
    apply_profile,
    counties_for_zip,
    is_marketplace_state,
    validate_profile,
)

bp = Blueprint("profile", __name__, url_prefix="/api")

_ZIP = re.compile(r"[0-9]{5}")


def _profile_response(user) -> dict:
    return ProfileResponse(
        zip_code=user.zip_code,
        date_of_birth=user.date_of_birth,
        county_fips=user.county_fips,
        county_name=user.county_name,
        state=user.state,
        marketplace_state=is_marketplace_state(user.state),
    ).model_dump(mode="json")


@bp.get("/profile")
@jwt_required()
@limiter.limit("60 per minute")
def get_profile():
    return jsonify(_profile_response(get_current_user()))


@bp.put("/profile")
@jwt_required()
@limiter.limit("10 per minute")
def update_profile():
    body = parse_body(ProfileUpdateRequest)
    db = get_db()
    user = get_current_user()

    try:
        county = validate_profile(db, zip_code=body.zip_code, date_of_birth=body.date_of_birth,
                                  county_fips=body.county_fips)
    except ProfileInvalidError as exc:
        raise ValidationFailedError(exc.errors) from None

    apply_profile(user, zip_code=body.zip_code, date_of_birth=body.date_of_birth, county=county)
    return jsonify(_profile_response(user))


@bp.get("/counties")
@limiter.limit("30 per minute")
def counties():
    """The counties a ZIP code lies in, for the signup form's county choice.

    Public, because signup comes before an account; the data is CMS's public
    crosswalk. Limited per IP address, since there is no token to key on.
    """
    zip_code = request.args.get("zip", "")
    if not _ZIP.fullmatch(zip_code):
        raise ValidationFailedError([{"field": "zip", "message": "Enter a 5-digit ZIP code."}])

    found = counties_for_zip(get_db(), zip_code)
    if not found:
        return jsonify(error="ZIP code not found"), 404
    return jsonify(CountiesResponse(
        counties=[CountyResponse(county_fips=c.fips, county_name=c.name, state=c.state) for c in found],
        # A ZIP code crossing into a marketplace state still counts: plan search uses those counties.
        marketplace_state=any(is_marketplace_state(c.state) for c in found),
    ).model_dump(mode="json"))
