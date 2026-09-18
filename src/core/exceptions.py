class EmailAlreadyRegisteredError(Exception):
    """Raised when registering an email that already has an account."""


class InvalidCredentialsError(Exception):
    """Raised when login email/password don't match a valid, active account."""


class MarketplaceApiKeyMissingError(Exception):
    """Raised when plan ingestion runs without CMS_MARKETPLACE_API_KEY set."""
