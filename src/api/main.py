from datetime import timedelta

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException

from src.api.deps import TokenBudgetExhaustedError, ValidationFailedError, close_db
from src.api.limiter import limiter
from src.api.routes.auth import bp as auth_bp
from src.api.routes.chat import bp as chat_bp
from src.core.logging import get_logger
from src.policypal.config import settings

logger = get_logger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)

    app.config["JWT_SECRET_KEY"] = settings.jwt_secret_key.get_secret_value()
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=settings.jwt_access_token_expires_minutes)
    # Exposes X-RateLimit-* and Retry-After on 429s so clients can back off correctly.
    app.config["RATELIMIT_HEADERS_ENABLED"] = True

    JWTManager(app)
    limiter.init_app(app)
    CORS(app, origins=[settings.frontend_origin])

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)

    app.teardown_appcontext(close_db)

    @app.errorhandler(ValidationFailedError)
    def _handle_validation_error(exc: ValidationFailedError):
        return jsonify(error="validation failed", details=exc.errors), 422

    @app.errorhandler(TokenBudgetExhaustedError)
    def _handle_token_budget(exc: TokenBudgetExhaustedError):
        # 429 like the rate limiter, but a distinct error string: "slow down"
        # and "you are done until tomorrow" need different handling client-side.
        response = jsonify(error="daily token budget exhausted")
        response.headers["Retry-After"] = str(exc.retry_after)
        return response, 429

    @app.errorhandler(Exception)
    def _handle_unexpected_error(exc: Exception):
        # Safety net: chat.py already handles an OpenAI failure specifically
        # (partial spend recorded, message kept). This exists so anything
        # else unhandled still returns JSON from a JSON API instead of
        # Flask's default HTML error page — never the exception body, which
        # can embed details (e.g. an upstream response) that must not reach
        # the client.
        if isinstance(exc, HTTPException):
            return exc
        logger.exception("unhandled error")
        return jsonify(error="internal server error"), 500

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return app


if __name__ == "__main__":
    create_app().run(debug=settings.environment == "development")
