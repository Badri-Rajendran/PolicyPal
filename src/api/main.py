from datetime import timedelta

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from src.api.deps import ValidationFailedError, close_db
from src.api.limiter import limiter
from src.api.routes.auth import bp as auth_bp
from src.api.routes.chat import bp as chat_bp
from src.policypal.config import settings


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

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return app


if __name__ == "__main__":
    create_app().run(debug=settings.environment == "development")
