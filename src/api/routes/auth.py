from flask import Blueprint, jsonify
from flask_jwt_extended import create_access_token, jwt_required

from src.api.deps import ValidationFailedError, get_current_user, get_db, parse_body
from src.api.limiter import limiter
from src.core.exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError
from src.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from src.services.auth import authenticate_user, register_user
from src.services.profile import ProfileInvalidError, apply_profile, validate_profile

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _token_response(user) -> dict:
    token = create_access_token(identity=str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user, from_attributes=True)).model_dump(
        mode="json"
    )


@bp.post("/register")
@limiter.limit("5 per minute")
def register():
    body = parse_body(RegisterRequest)
    db = get_db()

    # Before the account exists: an under-13 signup must write nothing (ADR 0012).
    try:
        county = validate_profile(db, zip_code=body.zip_code, date_of_birth=body.date_of_birth,
                                  county_fips=body.county_fips)
    except ProfileInvalidError as exc:
        raise ValidationFailedError(exc.errors) from None

    try:
        user = register_user(db, body.email, body.password)
    except EmailAlreadyRegisteredError:
        return jsonify(error="an account with this email already exists"), 409
    apply_profile(user, zip_code=body.zip_code, date_of_birth=body.date_of_birth, county=county)

    db.flush()
    return jsonify(_token_response(user)), 201


@bp.post("/login")
@limiter.limit("10 per minute")
def login():
    body = parse_body(LoginRequest)
    db = get_db()

    try:
        user = authenticate_user(db, body.email, body.password)
    except InvalidCredentialsError:
        return jsonify(error="invalid email or password"), 401

    return jsonify(_token_response(user))


@bp.get("/me")
@jwt_required()
@limiter.limit("60 per minute")
def me():
    user = get_current_user()
    return jsonify(UserResponse.model_validate(user, from_attributes=True).model_dump(mode="json"))
