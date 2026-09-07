class EmailAlreadyRegisteredError(Exception):
    """Raised when registering an email that already has an account."""


class InvalidCredentialsError(Exception):
    """Raised when login email/password don't match a valid, active account."""
