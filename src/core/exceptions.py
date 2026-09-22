class EmailAlreadyRegisteredError(Exception):
    """Raised when registering an email that already has an account."""


class InvalidCredentialsError(Exception):
    """Raised when login email/password don't match a valid, active account."""


class MarketplaceApiKeyMissingError(Exception):
    """Raised when a Marketplace API call is made without CMS_MARKETPLACE_API_KEY set."""


class MissingSearchIndexError(Exception):
    """Raised when the BM25 index has not been built into the database yet."""
