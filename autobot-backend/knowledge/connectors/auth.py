# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Typed auth dataclasses for connector credential configuration (Issue #8145).

Each dataclass represents one authentication pattern.  Connectors declare which
type they expect via ``AbstractConnector.auth_schema()``.  The API layer
validates incoming config dicts against the declared schema before persisting.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class BearerAuth:
    """Bearer-token authentication — Authorization: Bearer <token>."""

    token: str


@dataclass
class ApiKeyAuth:
    """API-key authentication passed as a request header or query parameter."""

    key: str
    header: str = "X-Api-Key"


@dataclass
class BasicAuth:
    """HTTP Basic authentication."""

    username: str
    password: str


@dataclass
class OAuthRefreshAuth:
    """OAuth 2.0 client-credentials / refresh-token flow."""

    client_id: str
    client_secret: str
    refresh_token: str
    token_url: str
    scopes: List[str] = field(default_factory=list)


# Registry used by the API validation layer to resolve auth type by name.
_AUTH_TYPES_BY_NAME: dict = {
    "BearerAuth": BearerAuth,
    "ApiKeyAuth": ApiKeyAuth,
    "BasicAuth": BasicAuth,
    "OAuthRefreshAuth": OAuthRefreshAuth,
}


def validate_config_against_schema(auth_cls: type, config: dict) -> list[str]:
    """Return a list of missing required fields for *auth_cls* given *config*.

    Returns an empty list when all required fields are present (validation passed).
    Only checks that required fields (those without defaults) are present; it does
    not type-coerce values.
    """
    import dataclasses

    errors: list[str] = []
    for f in dataclasses.fields(auth_cls):
        has_default = (
            f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING  # type: ignore[misc]
        )
        if not has_default and f.name not in config:
            errors.append("missing required auth field: %s" % f.name)
    return errors
