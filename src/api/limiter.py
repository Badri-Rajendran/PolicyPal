from flask_jwt_extended import get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _rate_limit_key() -> str:
    try:
        identity = get_jwt_identity()
    except RuntimeError:
        identity = None
    return identity or get_remote_address()


limiter = Limiter(key_func=_rate_limit_key, default_limits=["120 per minute"])
